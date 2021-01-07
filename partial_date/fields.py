# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import datetime
import re
import six

from django.core import exceptions
from django.db import models
from django.utils.translation import ugettext_lazy as _


partial_date_re = re.compile(
    r"^(?P<year>\d+)(?:-(?P<month>\d{1,2}))?(?:-(?P<day>\d{1,2}))?$"
)
partial_date_re_circa = re.compile( r"^(circa|c\.?)\s*(?P<year>\d+)$", re.IGNORECASE )


class PartialDate(object):
    YEAR = 0
    MONTH = 1
    DAY = 2
    # It might be better if the CIRCA flag was 0 
    # but this only works as a drop in for code already using PartialDate 
    # if it doesn't disturb the values that are already set
    CIRCA = 3

    _date = None
    _precision = None

    def __init__(self, date, precision=DAY):
        if isinstance(date, six.text_type):
            date, precision = PartialDate.parse_date(date)

        self.date = date
        self.precision = precision

    def __repr__(self):
        return (
            ""
            if not self._date
            else self.format()
        )

    def format(self, precision_year="%Y", precision_month="%Y-%m", precision_day="%Y-%m-%d", precision_circa="c. %Y"):
        if self.is_precision_year():
            format = precision_year
        elif self.is_precision_month():
            format = precision_month
        elif self.is_precision_circa():
            format = precision_circa
        else:
            format = precision_day
        return "" if not self._date else self._date.strftime(format)

    @property
    def date(self):
        return self._date

    @date.setter
    def date(self, value):
        if not isinstance(value, datetime.date):
            raise exceptions.ValidationError(
                _("%(value)s is not datetime.date instance"), params={"value": value}
            )
        self._date = value

    @property
    def precision(self):
        return self._precision

    @precision.setter
    def precision(self, value):
        self._precision = (
            value if value in (self.YEAR, self.MONTH, self.DAY, self.CIRCA) else self.DAY
        )
        if self._precision == self.MONTH:
            self._date.replace(day=1)
        elif self._precision == self.YEAR or self._precision == self.CIRCA:
            self._date.replace(month=1, day=1)

    def is_precision_year(self):
        return self.precision == self.YEAR

    def is_precision_month(self):
        return self.precision == self.MONTH

    def is_precision_day(self):
        return self.precision == self.DAY

    def is_precision_circa(self):
        return self.precision == self.CIRCA

    @staticmethod
    def parse_date(value):
        """
        Returns a tuple (datetime.date, precision) from a string formatted as YYYY, YYYY-MM, YYYY-MM-DD, c. YYYY, circa YYYY.
        """
        # Test if circa
        match = partial_date_re_circa.match(value)
        if match:
            match_dict = match.groupdict()
            date = datetime.date(
                year=int(match_dict['year']),
                month=1,
                day=1,
            )
            return (date, PartialDate.CIRCA)

        match = partial_date_re.match(value)

        try:
            match_dict = match.groupdict()
            kw = {k: int(v) if v else 1 for k, v in six.iteritems(match_dict)}

            precision = (
                PartialDate.DAY
                if match_dict["day"]
                else PartialDate.MONTH
                if match_dict["month"]
                else PartialDate.YEAR
            )
            
            return (datetime.date(**kw), precision)
        except (AttributeError, ValueError):
            raise exceptions.ValidationError(
                _("'%(value)s' is not a valid date string (YYYY, YYYY-MM, YYYY-MM-DD, c. YYYY, circa YYYY)"),
                params={"value": value},
            )

    def __eq__(self, other):
        if isinstance(other, PartialDate):
            return self.date == other.date and self.precision == other.precision
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, PartialDate):
            return self.__ge__(other) and not self.__eq__(other)
        else:
            return NotImplemented

    def __ge__(self, other):
        if isinstance(other, PartialDate):
            return self.date >= other.date and self.precision >= other.precision
        else:
            return NotImplemented


class PartialDateField(models.Field):
    """
    A django model field for storing partial dates.
    Accepts None, a partial_date.PartialDate object,
    or a formatted string such as YYYY, YYYY-MM, YYYY-MM-DD.
    In the database it saves the date in a column of type DateTimeField
    and uses the seconds to save the level of precision.
    """

    def get_internal_type(self):
        return "DateTimeField"

    def from_db_value(self, value, expression, connection, context=None):
        if value is None:
            return value
        return PartialDate(value.date(), value.second)

    def to_python(self, value):
        if value is None:
            return value

        if isinstance(value, PartialDate):
            return value

        if isinstance(value, six.text_type):
            return PartialDate(value)

        raise exceptions.ValidationError(
            _(
                "'%(name)s' value must be a PartialDate instance, "
                "a valid partial date string (YYYY, YYYY-MM, YYYY-MM-DD) "
                "or None, not '%(value)s'"
            ),
            params={"name": self.name, "value": value},
        )

    def get_prep_value(self, value):
        if value in (None, ""):
            return None
        partial_date = self.to_python(value)
        date = partial_date.date
        return datetime.datetime(
            date.year, date.month, date.day, second=partial_date.precision
        )
