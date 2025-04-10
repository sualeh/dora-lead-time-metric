"""Tests for the date_utility module."""

import pytest
from datetime import date
from dora_lead_time.date_utility import DateUtility, YearMonth, MonthBoundary


def test_get_months_between_same_month():
    """Test getting months between dates in the same month."""
    start_date = date(2023, 5, 1)
    end_date = date(2023, 5, 31)

    result = DateUtility.get_months_between(start_date, end_date)

    assert len(result) == 1
    assert result[0] == YearMonth(2023, 5)


def test_get_months_between_multiple_months():
    """Test getting months between dates spanning multiple months."""
    start_date = date(2023, 5, 15)
    end_date = date(2023, 8, 10)

    result = DateUtility.get_months_between(start_date, end_date)

    expected = [
        YearMonth(2023, 5),
        YearMonth(2023, 6),
        YearMonth(2023, 7),
        YearMonth(2023, 8),
    ]

    assert result == expected


def test_get_months_between_multiple_years():
    """Test getting months between dates spanning multiple years."""
    start_date = date(2022, 11, 20)
    end_date = date(2023, 2, 5)

    result = DateUtility.get_months_between(start_date, end_date)

    expected = [
        YearMonth(2022, 11),
        YearMonth(2022, 12),
        YearMonth(2023, 1),
        YearMonth(2023, 2),
    ]

    assert result == expected


def test_get_months_between_same_date():
    """Test getting months when start date equals end date."""
    test_date = date(2023, 6, 15)

    result = DateUtility.get_months_between(test_date, test_date)

    assert len(result) == 1
    assert result[0] == YearMonth(2023, 6)


def test_get_month_start_end_regular_month():
    """Test getting boundaries for a regular month."""
    result = DateUtility.get_month_start_end(2023, 5)

    assert result.year == 2023
    assert result.month == 5
    assert result.start_date == date(2023, 5, 1)
    assert result.end_date == date(2023, 5, 31)


def test_get_month_start_end_february_normal_year():
    """Test getting boundaries for February in a non-leap year."""
    result = DateUtility.get_month_start_end(2023, 2)

    assert result.start_date == date(2023, 2, 1)
    assert result.end_date == date(2023, 2, 28)


def test_get_month_start_end_february_leap_year():
    """Test getting boundaries for February in a leap year."""
    result = DateUtility.get_month_start_end(2024, 2)

    assert result.start_date == date(2024, 2, 1)
    assert result.end_date == date(2024, 2, 29)


def test_get_month_start_end_december():
    """Test getting boundaries for December, which needs special handling."""
    result = DateUtility.get_month_start_end(2023, 12)

    assert result.start_date == date(2023, 12, 1)
    assert result.end_date == date(2023, 12, 31)


def test_get_month_start_end_thirty_day_month():
    """Test getting boundaries for a 30-day month."""
    result = DateUtility.get_month_start_end(2023, 4)

    assert result.start_date == date(2023, 4, 1)
    assert result.end_date == date(2023, 4, 30)
