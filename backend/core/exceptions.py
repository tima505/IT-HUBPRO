"""
Единый формат ошибок API.

Любой ответ с ошибкой содержит `detail` — одно понятное сообщение для показа
пользователю (фронтенд выводит именно его). Ошибки по полям сохраняются как есть.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import serializers
from rest_framework.views import exception_handler as drf_exception_handler


def _first_message(errors):
    """Первое сообщение из вложенной структуры ошибок DRF + имя поля."""
    if isinstance(errors, dict):
        for field, value in errors.items():
            msg, _ = _first_message(value)
            if msg:
                return msg, field
    elif isinstance(errors, list):
        for value in errors:
            msg, field = _first_message(value)
            if msg:
                return msg, field
    elif errors:
        return str(errors), None
    return None, None


def _field_label(context, field):
    view = context.get('view')
    try:
        label = view.get_serializer().fields[field].label
    except Exception:
        return None
    return label


def validate_or_raise(serializer):
    """is_valid() для вспомогательных сериализаторов действий: `detail` с названием поля."""
    if serializer.is_valid():
        return
    errors = dict(serializer.errors)
    if 'detail' not in errors:
        msg, field = _first_message(errors)
        label = serializer.fields[field].label if field in serializer.fields else None
        errors['detail'] = f'{label}: {msg}' if label else msg
    raise serializers.ValidationError(errors)


def exception_handler(exc, context):
    if isinstance(exc, ProtectedError):
        exc = serializers.ValidationError(
            {'detail': 'Нельзя удалить: на запись ссылаются другие данные.'})
    elif isinstance(exc, DjangoValidationError):
        exc = serializers.ValidationError(exc.messages)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, list):
        data = response.data = {'errors': data}
    if isinstance(data, dict) and isinstance(data.get('detail'), list):
        data['detail'], _ = _first_message(data['detail'])
    if isinstance(data, dict) and 'detail' not in data:
        msg, field = _first_message(data)
        if msg:
            label = None if field in (None, 'non_field_errors', 'errors') else _field_label(context, field)
            data['detail'] = f'{label}: {msg}' if label else msg
    return response
