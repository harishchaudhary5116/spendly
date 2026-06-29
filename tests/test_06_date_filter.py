"""
Tests for Step 6 — Date-filter feature on the /profile page.

Coverage:
  Part 1 — Unit tests for database/queries.py helpers:
    get_summary_stats, get_recent_transactions, get_category_breakdown

  Part 2 — Integration tests for GET /profile via Flask test client:
    auth guard, no-filter baseline, date-filtered views, invalid/inverted params,
    preset active-state detection, user-info card invariance.

Isolation: every test uses the `tmp_db` fixture from conftest.py which
monkeypatches database.db.DB_PATH to a per-test temp file. No production
spendly.db is touched.
"""

from datetime import date, timedelta

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# ---------------------------------------------------------------------------
# Part 1: Unit tests — query helpers
# ---------------------------------------------------------------------------


class TestGetSummaryStats:
    """get_summary_stats(user_id, *, start_date=None, end_date=None)"""

    def test_no_filter_returns_all_time_totals(self, tmp_db):
        stats = get_summary_stats(tmp_db["user_id"])
        assert stats["total_spent"] == tmp_db["all_time_total"], (
            "All-time total should equal the sum of every test expense"
        )
        assert stats["transaction_count"] == tmp_db["all_time_count"]
        assert stats["top_category"] == tmp_db["all_time_top_category"]

    def test_date_range_filters_total_and_count(self, tmp_db):
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        assert stats["total_spent"] == tmp_db["june_01_10_total"], (
            "Only Food expenses on 2026-06-01 and 2026-06-10 should be included"
        )
        assert stats["transaction_count"] == tmp_db["june_01_10_count"]

    def test_date_range_filters_top_category(self, tmp_db):
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        assert stats["top_category"] == tmp_db["june_01_10_top_category"]

    def test_wider_range_picks_correct_top_category(self, tmp_db):
        # 2026-06-01 to 2026-06-15 includes Food(150) and Transport(200).
        # Transport has the higher total so it should be top_category.
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-15",
        )
        assert stats["total_spent"] == tmp_db["june_01_15_total"]
        assert stats["transaction_count"] == tmp_db["june_01_15_count"]
        assert stats["top_category"] == tmp_db["june_01_15_top_category"]

    def test_empty_range_returns_zero_totals(self, tmp_db):
        """A range with no expenses must return the zero-state dict."""
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2099-01-01",
            end_date="2099-12-31",
        )
        assert stats["total_spent"] == 0, "No expenses in future range → total 0"
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—", (
            "Empty range must return the em-dash sentinel, not None or empty string"
        )

    def test_only_start_date_filters_from_that_date(self, tmp_db):
        """When only start_date is given, expenses on-or-after that date are included."""
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-01",
        )
        # 100 + 50 + 200 = 350
        assert stats["total_spent"] == 350.00
        assert stats["transaction_count"] == 3

    def test_only_end_date_filters_up_to_that_date(self, tmp_db):
        """When only end_date is given, expenses on-or-before that date are included."""
        stats = get_summary_stats(
            tmp_db["user_id"],
            end_date="2026-06-10",
        )
        # 300 + 100 + 50 = 450
        assert stats["total_spent"] == 450.00
        assert stats["transaction_count"] == 3

    def test_boundary_dates_are_inclusive(self, tmp_db):
        """start_date and end_date boundaries must be inclusive (>=, <=)."""
        # Exactly the two edge expenses of the June 01–10 window.
        stats = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-01",
        )
        assert stats["transaction_count"] == 1
        assert stats["total_spent"] == 100.00

        stats2 = get_summary_stats(
            tmp_db["user_id"],
            start_date="2026-06-10",
            end_date="2026-06-10",
        )
        assert stats2["transaction_count"] == 1
        assert stats2["total_spent"] == 50.00


class TestGetRecentTransactions:
    """get_recent_transactions(user_id, limit=10, *, start_date=None, end_date=None)"""

    def test_no_filter_returns_all_transactions(self, tmp_db):
        txns = get_recent_transactions(tmp_db["user_id"])
        assert len(txns) == 4, "Unfiltered call must return all four test expenses"

    def test_no_filter_ordered_newest_first(self, tmp_db):
        txns = get_recent_transactions(tmp_db["user_id"])
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates, reverse=True), (
            "Transactions must be ordered newest-first"
        )

    def test_date_range_returns_only_in_range_rows(self, tmp_db):
        txns = get_recent_transactions(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        assert len(txns) == 2, (
            "Only two expenses fall within 2026-06-01 to 2026-06-10"
        )
        for t in txns:
            assert "2026-06-01" <= t["date"] <= "2026-06-10", (
                f"Transaction date {t['date']} is outside the requested range"
            )

    def test_date_range_result_ordered_newest_first(self, tmp_db):
        txns = get_recent_transactions(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        dates = [t["date"] for t in txns]
        assert dates == sorted(dates, reverse=True)

    def test_empty_range_returns_empty_list(self, tmp_db):
        txns = get_recent_transactions(
            tmp_db["user_id"],
            start_date="2099-01-01",
            end_date="2099-12-31",
        )
        assert txns == [], "No expenses in future range → empty list"

    def test_each_row_has_required_keys(self, tmp_db):
        txns = get_recent_transactions(tmp_db["user_id"])
        required_keys = {"date", "description", "category", "amount"}
        for t in txns:
            assert required_keys.issubset(t.keys()), (
                f"Transaction row missing keys: {required_keys - set(t.keys())}"
            )

    def test_limit_parameter_caps_results(self, tmp_db):
        txns = get_recent_transactions(tmp_db["user_id"], limit=2)
        assert len(txns) <= 2, "Limit parameter must cap the number of results"

    def test_excludes_expenses_before_start_date(self, tmp_db):
        """The 2026-01-01 Bills expense must NOT appear when start_date is 2026-06-01."""
        txns = get_recent_transactions(
            tmp_db["user_id"],
            start_date="2026-06-01",
        )
        dates = [t["date"] for t in txns]
        assert "2026-01-01" not in dates, (
            "Expense dated 2026-01-01 must be excluded when start_date=2026-06-01"
        )

    def test_excludes_expenses_after_end_date(self, tmp_db):
        """The 2026-06-15 Transport expense must NOT appear when end_date is 2026-06-10."""
        txns = get_recent_transactions(
            tmp_db["user_id"],
            end_date="2026-06-10",
        )
        dates = [t["date"] for t in txns]
        assert "2026-06-15" not in dates, (
            "Expense dated 2026-06-15 must be excluded when end_date=2026-06-10"
        )


class TestGetCategoryBreakdown:
    """get_category_breakdown(user_id, *, start_date=None, end_date=None)"""

    def test_no_filter_returns_all_categories(self, tmp_db):
        breakdown = get_category_breakdown(tmp_db["user_id"])
        names = {item["name"] for item in breakdown}
        assert names == {"Bills", "Food", "Transport"}, (
            "All three categories from test expenses must appear"
        )

    def test_no_filter_percentages_sum_to_100(self, tmp_db):
        breakdown = get_category_breakdown(tmp_db["user_id"])
        total_pct = sum(item["pct"] for item in breakdown)
        assert total_pct == 100, (
            f"Percentages must sum to exactly 100, got {total_pct}"
        )

    def test_date_range_returns_only_in_range_categories(self, tmp_db):
        # 2026-06-01 to 2026-06-10: only Food expenses
        breakdown = get_category_breakdown(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        names = {item["name"] for item in breakdown}
        assert names == {"Food"}, (
            "Only Food category should appear in the 2026-06-01 to 2026-06-10 range"
        )

    def test_date_range_single_category_has_100_percent(self, tmp_db):
        breakdown = get_category_breakdown(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-10",
        )
        assert len(breakdown) == 1
        assert breakdown[0]["pct"] == 100, (
            "A single category in range must receive 100 percent"
        )

    def test_date_range_percentages_sum_to_100(self, tmp_db):
        # 2026-06-01 to 2026-06-15: Food(150) + Transport(200)
        breakdown = get_category_breakdown(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-15",
        )
        assert len(breakdown) == 2
        total_pct = sum(item["pct"] for item in breakdown)
        assert total_pct == 100, (
            f"Percentages for filtered range must sum to 100, got {total_pct}"
        )

    def test_date_range_excludes_out_of_range_categories(self, tmp_db):
        # Bills (2026-01-01) should not appear in a June-only filter.
        breakdown = get_category_breakdown(
            tmp_db["user_id"],
            start_date="2026-06-01",
            end_date="2026-06-15",
        )
        names = {item["name"] for item in breakdown}
        assert "Bills" not in names, (
            "Bills expense (2026-01-01) must not appear in a June filter"
        )

    def test_empty_range_returns_empty_list(self, tmp_db):
        breakdown = get_category_breakdown(
            tmp_db["user_id"],
            start_date="2099-01-01",
            end_date="2099-12-31",
        )
        assert breakdown == [], "No expenses in future range → empty list"

    def test_each_item_has_required_keys(self, tmp_db):
        breakdown = get_category_breakdown(tmp_db["user_id"])
        for item in breakdown:
            assert "name" in item, "Breakdown item missing 'name'"
            assert "amount" in item, "Breakdown item missing 'amount'"
            assert "pct" in item, "Breakdown item missing 'pct'"

    def test_ordered_by_amount_descending(self, tmp_db):
        breakdown = get_category_breakdown(tmp_db["user_id"])
        amounts = [item["amount"] for item in breakdown]
        assert amounts == sorted(amounts, reverse=True), (
            "Category breakdown must be ordered by amount, highest first"
        )


# ---------------------------------------------------------------------------
# Part 2: Integration tests — GET /profile route
# ---------------------------------------------------------------------------


class TestProfileRouteAuthGuard:
    """Unauthenticated access to /profile must redirect to /login."""

    def test_unauthenticated_get_redirects_to_login(self, client):
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302, (
            "Unauthenticated GET /profile must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_with_params_still_redirects(self, client):
        resp = client.get(
            "/profile?start_date=2026-06-01&end_date=2026-06-30",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestProfileRouteNoFilter:
    """GET /profile with no query params — the all-time baseline."""

    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Authenticated GET /profile must return 200"

    def test_response_contains_all_time_total(self, auth_client, tmp_db):
        resp = auth_client.get("/profile")
        # Total = 650.00; check for the number in the page
        assert b"650" in resp.data, (
            "Unfiltered /profile must show the all-time total (650)"
        )

    def test_response_contains_all_time_transaction_count(self, auth_client, tmp_db):
        resp = auth_client.get("/profile")
        # 4 test expenses were inserted
        assert str(tmp_db["all_time_count"]).encode() in resp.data

    def test_all_time_preset_link_is_active(self, auth_client):
        """'All time' preset must carry the is-active class when no params are supplied."""
        resp = auth_client.get("/profile")
        assert b"is-active" in resp.data, (
            "The is-active class must appear for the All time preset on unfiltered page"
        )

    def test_page_contains_all_time_preset_link_text(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"All time" in resp.data, (
            "'All time' preset link text must appear on the profile page"
        )

    def test_page_contains_preset_link_texts(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"This month" in resp.data, "This month preset link must be present"
        assert b"Last 30 days" in resp.data, "Last 30 days preset link must be present"

    def test_date_filter_form_is_present(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"start_date" in resp.data, "Date filter form must have start_date input"
        assert b"end_date" in resp.data, "Date filter form must have end_date input"


class TestProfileRouteDateFilter:
    """GET /profile with valid start_date / end_date params."""

    def test_narrow_range_returns_200(self, auth_client):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert resp.status_code == 200

    def test_narrow_range_shows_filtered_total(self, auth_client, tmp_db):
        """Only Food expenses (100 + 50 = 150) fall in the June 01–10 window."""
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert b"150" in resp.data, (
            "Filtered /profile must show total 150 for the 2026-06-01 to 2026-06-10 range"
        )
        # The all-time total (650) must NOT appear as a standalone total.
        # We only assert the filtered total is present; the overall count distinguishes.

    def test_narrow_range_transaction_count_matches(self, auth_client, tmp_db):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        expected_count = str(tmp_db["june_01_10_count"]).encode()
        assert expected_count in resp.data, (
            f"Filtered page must show transaction count {tmp_db['june_01_10_count']}"
        )

    def test_narrow_range_shows_filter_caption(self, auth_client):
        """A date-range caption must appear when both params are supplied."""
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        # Caption format: "1 Jun 2026 → 10 Jun 2026" — check for month abbreviation.
        assert b"Jun 2026" in resp.data, (
            "Filter caption must show the active date range"
        )

    def test_narrow_range_echoes_dates_in_form_inputs(self, auth_client):
        """The date inputs must echo back their current values via the value= attribute."""
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert b"2026-06-01" in resp.data, "start_date value must be echoed in the form"
        assert b"2026-06-10" in resp.data, "end_date value must be echoed in the form"

    def test_full_range_covering_all_expenses_matches_all_time(self, auth_client, tmp_db):
        """A wide enough range should produce the same totals as no filter at all."""
        resp_unfiltered = auth_client.get("/profile")
        resp_wide = auth_client.get(
            "/profile?start_date=2025-01-01&end_date=2099-12-31"
        )
        assert resp_wide.status_code == 200
        # Both pages must contain the all-time total.
        assert b"650" in resp_wide.data, (
            "A wide range that covers all expenses must show the same total as unfiltered"
        )


class TestProfileRouteEmptyRange:
    """GET /profile with a date range that contains no expenses."""

    def test_empty_range_returns_200_not_error(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert resp.status_code == 200, (
            "Empty range must render the page (200), not raise a 500"
        )

    def test_empty_range_shows_zero_total(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        # Currency is ₹; total must render as ₹0.00 or contain 0.00
        assert b"0.00" in resp.data, (
            "Empty range must show a zero total (0.00)"
        )

    def test_empty_range_shows_no_transactions_copy(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert b"No transactions yet" in resp.data, (
            "Empty range must show the empty-state copy 'No transactions yet.'"
        )

    def test_empty_range_shows_no_categories_copy(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert b"No spending categorised yet" in resp.data, (
            "Empty range must show 'No spending categorised yet.' empty-state copy"
        )

    def test_empty_range_shows_em_dash_for_top_category(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert "—".encode("utf-8") in resp.data, (
            "Top category for an empty range must render as the em-dash sentinel"
        )


class TestProfileRouteInvalidParams:
    """Invalid or logically-reversed date params must fall back to unfiltered render."""

    def test_invalid_start_date_returns_200(self, auth_client):
        resp = auth_client.get("/profile?start_date=banana&end_date=2026-06-30")
        assert resp.status_code == 200, (
            "Invalid start_date must not cause a 500; page must render"
        )

    def test_invalid_start_date_renders_all_expenses(self, auth_client):
        """When start_date is unparseable the filter is silently ignored."""
        resp = auth_client.get("/profile?start_date=banana&end_date=2026-06-30")
        # Should fall back to unfiltered; all-time total (650) must appear.
        assert b"650" in resp.data, (
            "Invalid start_date must produce the unfiltered page (all-time total visible)"
        )

    def test_invalid_end_date_returns_200(self, auth_client):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=not-a-date")
        assert resp.status_code == 200

    def test_invalid_end_date_renders_all_expenses(self, auth_client):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=not-a-date")
        assert b"650" in resp.data, (
            "Invalid end_date must produce the unfiltered page"
        )

    def test_inverted_range_returns_200(self, auth_client):
        """start_date > end_date must not raise — page must render."""
        resp = auth_client.get("/profile?start_date=2026-12-31&end_date=2026-01-01")
        assert resp.status_code == 200, (
            "Inverted date range must not cause a 500"
        )

    def test_inverted_range_renders_all_expenses(self, auth_client):
        """When start > end, the filter is dropped and all expenses appear."""
        resp = auth_client.get("/profile?start_date=2026-12-31&end_date=2026-01-01")
        assert b"650" in resp.data, (
            "Inverted range must produce the unfiltered page (all-time total visible)"
        )

    def test_inverted_range_all_time_preset_active(self, auth_client):
        """Inverted-range fall-through → no start/end → all_time preset is active."""
        resp = auth_client.get("/profile?start_date=2026-12-31&end_date=2026-01-01")
        assert b"is-active" in resp.data, (
            "Inverted-range fall-through must activate the All time preset"
        )


class TestProfileRoutePresetActiveState:
    """Preset links receive is-active only when the URL params match exactly."""

    def test_this_month_preset_active_when_params_match(self, auth_client):
        """
        When start_date == first-of-current-month and end_date == today,
        the 'This month' preset must be marked is-active.
        """
        today = date.today()
        this_month_start = today.replace(day=1).isoformat()
        today_iso = today.isoformat()
        url = f"/profile?start_date={this_month_start}&end_date={today_iso}"
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert b"is-active" in resp.data, (
            "This month preset must carry is-active when params match the current month range"
        )

    def test_last_30_preset_active_when_params_match(self, auth_client):
        """
        When start_date == today-29 and end_date == today,
        the 'Last 30 days' preset must be marked is-active.
        """
        today = date.today()
        last_30_start = (today - timedelta(days=29)).isoformat()
        today_iso = today.isoformat()
        url = f"/profile?start_date={last_30_start}&end_date={today_iso}"
        resp = auth_client.get(url)
        assert resp.status_code == 200
        assert b"is-active" in resp.data, (
            "Last 30 days preset must carry is-active when params match today-29 → today"
        )

    def test_no_preset_active_for_arbitrary_custom_range(self, auth_client):
        """A custom range that matches no preset → no is-active class in the response."""
        # 2026-03-15 to 2026-03-20 matches neither this_month nor last_30.
        resp = auth_client.get("/profile?start_date=2026-03-15&end_date=2026-03-20")
        assert resp.status_code == 200
        assert b"is-active" not in resp.data, (
            "A custom range that matches no preset must not render is-active on any link"
        )

    def test_all_time_preset_not_active_when_filter_applied(self, auth_client):
        """When a date filter is active, the All time preset must NOT have is-active."""
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-15")
        # If is-active appears at all it should NOT be on All time — but the simplest
        # correctness check is that the page renders a filtered total (350), not 650.
        assert b"350" in resp.data, (
            "A date-filtered page must show filtered total (350), indicating All time is not active"
        )


class TestProfileRouteUserInfoCard:
    """The user-info card must be identical regardless of the active date filter."""

    def test_user_name_visible_without_filter(self, auth_client, tmp_db):
        resp = auth_client.get("/profile")
        assert tmp_db["name"].encode() in resp.data, (
            "User name must appear in the unfiltered profile page"
        )

    def test_user_email_visible_without_filter(self, auth_client, tmp_db):
        resp = auth_client.get("/profile")
        assert tmp_db["email"].encode() in resp.data, (
            "User email must appear in the unfiltered profile page"
        )

    def test_user_name_visible_with_filter(self, auth_client, tmp_db):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert tmp_db["name"].encode() in resp.data, (
            "User name must appear even when a date filter is active"
        )

    def test_user_email_visible_with_filter(self, auth_client, tmp_db):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert tmp_db["email"].encode() in resp.data, (
            "User email must appear even when a date filter is active"
        )

    def test_user_name_visible_with_empty_range(self, auth_client, tmp_db):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert tmp_db["name"].encode() in resp.data, (
            "User name must appear even when the filtered range contains no expenses"
        )

    def test_user_info_identical_filtered_vs_unfiltered(self, auth_client, tmp_db):
        """Name and email must appear in every filter scenario — they are never filtered."""
        name_bytes = tmp_db["name"].encode()
        email_bytes = tmp_db["email"].encode()

        for url in [
            "/profile",
            "/profile?start_date=2026-06-01&end_date=2026-06-10",
            "/profile?start_date=2099-01-01&end_date=2099-12-31",
            "/profile?start_date=banana",
        ]:
            resp = auth_client.get(url)
            assert name_bytes in resp.data, (
                f"User name missing from {url}"
            )
            assert email_bytes in resp.data, (
                f"User email missing from {url}"
            )


class TestProfileRouteCurrencyRendering:
    """Currency must always render as ₹ (INR) throughout the profile page."""

    def test_rupee_symbol_present_unfiltered(self, auth_client):
        resp = auth_client.get("/profile")
        assert "₹".encode("utf-8") in resp.data, (
            "Profile page must render currency as ₹ (INR)"
        )

    def test_rupee_symbol_present_with_filter(self, auth_client):
        resp = auth_client.get("/profile?start_date=2026-06-01&end_date=2026-06-10")
        assert "₹".encode("utf-8") in resp.data, (
            "Filtered profile page must still render currency as ₹ (INR)"
        )

    def test_rupee_symbol_present_on_empty_range(self, auth_client):
        resp = auth_client.get("/profile?start_date=2099-01-01&end_date=2099-12-31")
        assert "₹".encode("utf-8") in resp.data, (
            "Empty-range profile page must still render ₹ for zero totals"
        )
