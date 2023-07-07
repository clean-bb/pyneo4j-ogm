"""
This module contains custom datatypes which can be used to declare additional options for a property
like indexing or a unique constraint.
"""
from typing import Type, TypeVar

T = TypeVar("T")


def WithOptions(
    property_type: T,
    range_index: bool = False,
    text_index: bool = False,
    point_index: bool = False,
    unique: bool = False,
    ref: str | None = None,
) -> Type[T]:
    """
    Returns a subclass of `property_type` which includes extra attributes which can be used to define indexes and
    constraints on the property. Does not have an effect when called with just the `property_type` argument.

    Args:
        property_type (Any): The property type to return for the model field
        range_index (bool, optional): Whether the property should have a `RANGE` index or not. Defaults to False.
        text_index (bool, optional): Whether the property should have a `TEXT` index or not. Defaults to False.
        point_index (bool, optional): Whether the property should have a `POINT` index or not. Defaults to False.
        unique (bool, optional): Whether a `UNIQUENESS` constraint should be created for the property.
            Defaults to False.

    Returns:
        A subclass of the provided type with extra attributes
    """

    class PropertyWithOptions(property_type):
        """
        Subclass of provided type with extra arguments
        """

        _range_index: bool = range_index
        _text_index: bool = text_index
        _point_index: bool = point_index
        _unique: bool = unique
        _ref: str | None = ref

        def __new__(cls, *args, **kwargs) -> object:
            return property_type.__new__(property_type, *args, **kwargs)

    return PropertyWithOptions
