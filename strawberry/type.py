from functools import partial

import dataclasses
from graphql import GraphQLInputObjectType, GraphQLInterfaceType, GraphQLObjectType
from graphql.utilities.schema_printer import print_type

from .constants import IS_STRAWBERRY_FIELD, IS_STRAWBERRY_INPUT, IS_STRAWBERRY_INTERFACE
from .field import field, strawberry_field
from .type_converter import REGISTRY
from .utils.str_converters import to_camel_case


def _get_resolver(cls, field_name):
    class_field = getattr(cls, field_name, None)

    if class_field and getattr(class_field, "resolver", None):
        return class_field.resolver

    def _resolver(root, info):
        field_resolver = getattr(cls(**(root.__dict__ if root else {})), field_name)

        if getattr(field_resolver, IS_STRAWBERRY_FIELD, False):
            return field_resolver(root, info)

        elif field_resolver.__class__ is strawberry_field:
            # TODO: support default values
            return None

        return field_resolver

    return _resolver


def _process_type(cls, *, is_input=False, is_interface=False, description=None):
    name = cls.__name__
    REGISTRY[name] = cls

    def repr_(self):
        return print_type(self.field)

    setattr(cls, "__repr__", repr_)

    def _get_fields(wrapped):
        class_fields = dataclasses.fields(wrapped)

        fields = {}

        for class_field in class_fields:
            f = getattr(cls, class_field.name, None)
            field_name = getattr(f, "name", None) or to_camel_case(class_field.name)
            description = getattr(f, "description", None)

            resolver = _get_resolver(cls, class_field.name)
            resolver.__annotations__["return"] = class_field.type

            fields[field_name] = field(
                resolver, is_input=is_input, description=description
            ).field

        strawberry_fields = {
            key: value
            for key, value in cls.__dict__.items()
            if getattr(value, IS_STRAWBERRY_FIELD, False)
        }

        for key, value in strawberry_fields.items():
            name = getattr(value, "name", None) or to_camel_case(key)

            fields[name] = value.field

        return fields

    if is_input:
        setattr(cls, IS_STRAWBERRY_INPUT, True)
    elif is_interface:
        setattr(cls, IS_STRAWBERRY_INTERFACE, True)

    extra_kwargs = {"description": description or cls.__doc__}

    if is_input:
        TypeClass = GraphQLInputObjectType
    elif is_interface:
        TypeClass = GraphQLInterfaceType
    else:
        TypeClass = GraphQLObjectType

        extra_kwargs["interfaces"] = [
            klass.field
            for klass in cls.__bases__
            if hasattr(klass, IS_STRAWBERRY_INTERFACE)
        ]

    wrapped = dataclasses.dataclass(cls, repr=False)
    wrapped.field = TypeClass(name, lambda: _get_fields(wrapped), **extra_kwargs)

    return wrapped


def type(cls=None, *, is_input=False, is_interface=False, description=None):
    """Annotates a class as a GraphQL type.

    Example usage:

    >>> @strawberry.type:
    >>> class X:
    >>>     field_abc: str = "ABC"
    """

    def wrap(cls):
        return _process_type(
            cls, is_input=is_input, is_interface=is_interface, description=description
        )

    if cls is None:
        return wrap

    return wrap(cls)


input = partial(type, is_input=True)
interface = partial(type, is_interface=True)
