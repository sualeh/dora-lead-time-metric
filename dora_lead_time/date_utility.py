"""Do date operations for charts."""

from datetime import date, timedelta
from collections import namedtuple

# Define named tuples
YearMonth = namedtuple(
    'YearMonth',
    ['year', 'month']
)
MonthBoundary = namedtuple(
    'MonthBoundary',
    ['year', 'month', 'start_date', 'end_date']
)


class DateUtility:
    """Do date operations for charts."""

    @staticmethod
    def get_months_between(
        start_date: date, end_date: date
    ) -> list[YearMonth]:
        """
        Returns a list of YearMonth between start_date
        and end_date, inclusive.

        Args:
            start_date: The starting date
            end_date: The ending date

        Returns:
            A list of YearMonth named tuples with 'year' and 'month' attributes
        """
        months = []

        # Extract year and month from start and end dates
        start_year, start_month = start_date.year, start_date.month
        end_year, end_month = end_date.year, end_date.month

        # Generate all months between start and end dates
        current_year, current_month = start_year, start_month

        while (
            current_year < end_year or
            (current_year == end_year and current_month <= end_month)
        ):
            months.append(YearMonth(current_year, current_month))

            # Move to next month
            if current_month == 12:
                current_month = 1
                current_year += 1
            else:
                current_month += 1

        return months

    @staticmethod
    def get_month_start_end(year: int, month: int) -> MonthBoundary:
        """
        Get the start and end dates for a given year and month.

        Args:
            year: The year as an integer
            month: The month as an integer (1-12)

        Returns:
            A MonthBoundary named tuple with attributes:
            - year: the input year
            - month: the input month
            - start_date: the first day of the month
            - end_date: the last day of the month
        """
        # Start date: first day of the month
        start_date = date(year, month, 1)

        # End date: first day of the next month minus one day
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        return MonthBoundary(year, month, start_date, end_date)


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
