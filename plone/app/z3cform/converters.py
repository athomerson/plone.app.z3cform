# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import safe_callable
from datetime import date
from datetime import datetime
from plone.namedfile.interfaces import INamedField
from plone.uuid.interfaces import IUUID
from z3c.form.converter import BaseDataConverter
from z3c.form.converter import CollectionSequenceDataConverter
from z3c.form.converter import SequenceDataConverter
from z3c.form.interfaces import IAddForm
from z3c.form.interfaces import IDataManager
from z3c.form.interfaces import NO_VALUE
from zope.component import adapts
from zope.component import queryMultiAdapter
from zope.component.hooks import getSite
from zope.schema.interfaces import ICollection
from zope.schema.interfaces import IDate
from zope.schema.interfaces import IDatetime
from zope.schema.interfaces import IField
from zope.schema.interfaces import IList
from zope.schema.interfaces import ISequence

from plone.app.z3cform.interfaces import (
    IDateWidget, IDatetimeWidget, ISelectWidget, IAjaxSelectWidget,
    IRelatedItemsWidget, IQueryStringWidget, IFileUploadWidget)

import pytz
import json

from z3c.relationfield.interfaces import IRelationChoice
from z3c.relationfield.interfaces import IRelationList


class DateWidgetConverter(BaseDataConverter):
    """Data converter for date fields."""

    adapts(IDate, IDateWidget)

    def toWidgetValue(self, value):
        """Converts from field value to widget.

        :param value: Field value.
        :type value: date

        :returns: Date in format `Y-m-d`
        :rtype: string
        """
        if value is self.field.missing_value:
            return u''
        return ('{value.year:}-{value.month:02}-{value.day:02}'
                ).format(value=value)

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: Value inserted by date widget.
        :type value: string

        :returns: `date.date` object.
        :rtype: date
        """
        if not value:
            return self.field.missing_value
        return date(*map(int, value.split('-')))


class DatetimeWidgetConverter(BaseDataConverter):
    """Data converter for datetime fields."""

    adapts(IDatetime, IDatetimeWidget)

    def toWidgetValue(self, value):
        """Converts from field value to widget.

        :param value: Field value.
        :type value: datetime

        :returns: Datetime in format `Y-m-d H:M`
        :rtype: string
        """
        if value is self.field.missing_value:
            return u''
        return ('{value.year:}-{value.month:02}-{value.day:02} '
                '{value.hour:02}:{value.minute:02}').format(value=value)

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: Value inserted by datetime widget.
        :type value: string

        :returns: `datetime.datetime` object.
        :rtype: datetime
        """
        if not value:
            return self.field.missing_value
        tmp = value.split(' ')
        if not tmp[0]:
            return self.field.missing_value
        value = tmp[0].split('-')
        if len(tmp) == 2 and ':' in tmp[1]:
            value += tmp[1].split(':')
        else:
            value += ['00', '00']

        # TODO: respect the selected zone from the widget and just fall back
        # to default_zone
        default_zone = self.widget.default_timezone
        zone = default_zone(self.widget.context)\
            if safe_callable(default_zone) else default_zone
        ret = datetime(*map(int, value))
        if zone:
            tzinfo = pytz.timezone(zone)
            ret = tzinfo.localize(ret)
        return ret


class SelectWidgetConverterBase(object):

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: Value inserted by Select2 widget or default html
                      select/multi-select
        :type value: string | list

        :returns: List of items
        :rtype: list | tuple | set
        """
        separator = getattr(self.widget, 'separator', ';')
        if isinstance(value, basestring):
            value = value.strip()
            if value:
                value = value.split(separator)
            else:
                return self.field.missing_value
        elif value == (u'',):
            return self.field.missing_value
        return super(SelectWidgetConverterBase, self).toFieldValue(value)


class SequenceSelectWidgetConverter(
        SelectWidgetConverterBase, SequenceDataConverter):
    adapts(IField, ISelectWidget)


class SelectWidgetConverter(
        SelectWidgetConverterBase, CollectionSequenceDataConverter):
    adapts(ICollection, ISelectWidget)


class AjaxSelectWidgetConverter(BaseDataConverter):
    """Data converter for ICollection fields using the AjaxSelectWidget.
    """

    adapts(ICollection, IAjaxSelectWidget)

    def toWidgetValue(self, value):
        """Converts from field value to widget.

        :param value: Field value.
        :type value: list |tuple | set

        :returns: Items separated using separator defined on widget
        :rtype: string
        """
        if not value:
            return self.field.missing_value
        separator = getattr(self.widget, 'separator', ';')
        return separator.join(unicode(v) for v in value)

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: Value inserted by AjaxSelect widget.
        :type value: string

        :returns: List of items
        :rtype: list | tuple | set
        """
        collectionType = self.field._type
        if isinstance(collectionType, tuple):
            collectionType = collectionType[-1]
        if not len(value):
            return self.field.missing_value
        valueType = self.field.value_type._type
        if isinstance(valueType, tuple):
            valueType = valueType[0]
        separator = getattr(self.widget, 'separator', ';')
        return collectionType(valueType and valueType(v) or v
                              for v in value.split(separator))


class RelationChoiceRelatedItemsWidgetConverter(BaseDataConverter):
    """Data converter for RelationChoice fields using the RelatedItemsWidget.
    """

    adapts(IRelationChoice, IRelatedItemsWidget)

    def toWidgetValue(self, value):
        if not value:
            return self.field.missing_value
        return IUUID(value)

    def toFieldValue(self, value):
        if not value:
            return self.field.missing_value
        try:
            catalog = getToolByName(self.widget.context, 'portal_catalog')
        except AttributeError:
            catalog = getToolByName(getSite(), 'portal_catalog')

        res = catalog(UID=value)
        if res:
            return res[0].getObject()
        else:
            return self.field.missing_value


class RelatedItemsDataConverter(BaseDataConverter):
    """Data converter for ICollection fields using the RelatedItemsWidget."""

    adapts(ICollection, IRelatedItemsWidget)

    def toWidgetValue(self, value):
        """Converts from field value to widget.

        :param value: List of catalog brains.
        :type value: list

        :returns: List of of UID separated by separator defined on widget.
        :rtype: string
        """
        if not value:
            return self.field.missing_value
        separator = getattr(self.widget, 'separator', ';')
        if IRelationList.providedBy(self.field):
            return separator.join([IUUID(o) for o in value if value])
        else:
            return separator.join(v for v in value if v)

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: List of UID's separated by separator defined
        :type value: string

        :returns: List of content objects
        :rtype: list | tuple | set
        """
        if not value:
            return self.field.missing_value

        collectionType = self.field._type
        if isinstance(collectionType, tuple):
            collectionType = collectionType[-1]

        separator = getattr(self.widget, 'separator', ';')
        value = value.split(separator)

        if IRelationList.providedBy(self.field):
            try:
                catalog = getToolByName(self.widget.context, 'portal_catalog')
            except AttributeError:
                catalog = getToolByName(getSite(), 'portal_catalog')

            objects = {item.UID: item.getObject()
                       for item in catalog(UID=value) if item}

            return collectionType(objects[uid]
                                  for uid in value
                                  if uid in objects.keys())
        else:
            return collectionType(v for v in value)


class QueryStringDataConverter(BaseDataConverter):
    """Data converter for IList."""

    adapts(IList, IQueryStringWidget)

    def toWidgetValue(self, value):
        """Converts from field value to widget.

        :param value: Query string.
        :type value: list

        :returns: Query string converted to JSON.
        :rtype: string
        """
        if not value:
            return '[]'
        return json.dumps(value)

    def toFieldValue(self, value):
        """Converts from widget value to field.

        :param value: Query string.
        :type value: string

        :returns: Query string.
        :rtype: list
        """
        try:
            value = json.loads(value)
        except ValueError:
            value = None
        if not value:
            return self.field.missing_value
        return value

class FileUploadConverterBase(BaseDataConverter):
    """Converter for multi file widgets used on `schema.List` fields.
       Also a converter for single file widgets used on namedfile fields
       """

#    adapts(ISequence, IFileUploadWidget)

    def toWidgetValue(self, value):
        """Converts the value to a form used by the widget.
            For some reason this never gets called for File Uploads
            """
        return value

    def toFieldValue(self, value):
        """Converts the value to a storable form."""
        context = self.widget.context
        if not IAddForm.providedBy(self.widget.form):
            dm = queryMultiAdapter((context, self.field), IDataManager)
        else:
            dm = None

        current_field_value = (
            dm.query()
            if ((dm is not None) and self.field.interface.providedBy(context))
            else None
        )
        if not current_field_value or current_field_value == NO_VALUE:
            current_field_value = []
        if not isinstance(current_field_value, list):
            current_field_value = [current_field_value]
        current_field_set = set(current_field_value)
        retvalue = []
        if (INamedField.providedBy(self.field)):
            value_type = self.field._type
        else:
            value_type = self.field.value_type._type
        if not value:
            return value
        elif not isinstance(value, list):
            value = [value]
        for item in value:
            if item['new']:
                retvalue.append(value_type(data=item['file'].read(),
                                filename=item['name']))
            else:
                for existing_file in current_field_set:
                    if existing_file.filename == item['name']:
                        retvalue.append(existing_file)
        if (INamedField.providedBy(self.field)):
            return retvalue[0]
        else:
            return retvalue


class FileUploadConverter(FileUploadConverterBase):
    adapts(INamedField, IFileUploadWidget)


class MultiFileUploadConverter(FileUploadConverterBase):
    adapts(ISequence, IFileUploadWidget)

