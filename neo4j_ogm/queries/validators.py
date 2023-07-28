"""
This module contains pydantic models for validating and normalizing query filters.
"""
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Extra, Field, ValidationError, root_validator

from neo4j_ogm.queries.types import NumericQueryDataType, QueryDataTypes


def _normalize_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
    validated_values: Dict[str, Any] = deepcopy(values)

    for property_name, property_value in values.items():
        if property_name not in cls.__fields__.keys():
            try:
                validated = QueryOperatorModel.parse_obj(property_value)
                validated_values[property_name] = validated.dict(by_alias=True, exclude_none=True, exclude_unset=True)
            except ValidationError:
                validated_values.pop(property_name)
                logging.debug("Invalid field %s found, omitting field", property_name)

    return validated_values


class NumericEqualsOperatorModel(BaseModel):
    """
    Validator for `$eq` operator in combined use with `$size` operator.
    """

    eq: QueryDataTypes = Field(alias="$eq")


class NumericGreaterThanOperatorModel(BaseModel):
    """
    Validator for `$gt` operator in combined use with `$size` operator.
    """

    gt: QueryDataTypes = Field(alias="$gt")


class NumericGreaterThanEqualsOperatorModel(BaseModel):
    """
    Validator for `$gte` operator in combined use with `$size` operator.
    """

    gte: QueryDataTypes = Field(alias="$gte")


class NumericLessThanOperatorModel(BaseModel):
    """
    Validator for `$lt` operator in combined use with `$size` operator.
    """

    lt: QueryDataTypes = Field(alias="$lt")


class NumericLessThanEqualsOperatorModel(BaseModel):
    """
    Validator for `$lte` operator in combined use with `$size` operator.
    """

    lte: QueryDataTypes = Field(alias="$lte")


class QueryOperatorModel(BaseModel):
    """
    Validator for query operators defined in a property.
    """

    eq: Optional[QueryDataTypes] = Field(alias="$eq")
    neq: Optional[QueryDataTypes] = Field(alias="$neq")
    gt: Optional[NumericQueryDataType] = Field(alias="$gt")
    gte: Optional[NumericQueryDataType] = Field(alias="$gte")
    lt: Optional[NumericQueryDataType] = Field(alias="$lt")
    lte: Optional[NumericQueryDataType] = Field(alias="$lte")
    in_: Optional[Union[QueryDataTypes, List[QueryDataTypes]]] = Field(alias="$in")
    nin: Optional[Union[QueryDataTypes, List[QueryDataTypes]]] = Field(alias="$nin")
    all: Optional[List[QueryDataTypes]] = Field(alias="$all")
    size: Optional[
        Union[
            NumericQueryDataType,
            NumericEqualsOperatorModel,
            NumericGreaterThanOperatorModel,
            NumericGreaterThanEqualsOperatorModel,
            NumericLessThanOperatorModel,
            NumericLessThanEqualsOperatorModel,
        ]
    ] = Field(alias="$size")
    contains: Optional[str] = Field(alias="$contains")
    i_contains: Optional[str] = Field(alias="$icontains")
    starts_with: Optional[str] = Field(alias="$startsWith")
    i_starts_with: Optional[str] = Field(alias="$istartsWith")
    ends_with: Optional[str] = Field(alias="$endsWith")
    i_ends_with: Optional[str] = Field(alias="$iendsWith")
    regex: Optional[str] = Field(alias="$regex")
    not_: Optional["QueryOperatorModel"] = Field(alias="$not")
    and_: Optional[List["QueryOperatorModel"]] = Field(alias="$and")
    or_: Optional[List["QueryOperatorModel"]] = Field(alias="$or")
    xor: Optional[List["QueryOperatorModel"]] = Field(alias="$xor")


class NodeFiltersModel(BaseModel):
    """
    Validator model for node filters.
    """

    element_id: Optional[str] = Field(alias="$elementId")
    id: Optional[int] = Field(alias="$id")
    labels: Optional[Union[str, List[str]]] = Field(alias="$labels")

    normalize_and_validate_fields = root_validator(allow_reuse=True)(_normalize_fields)

    class Config:
        """
        Pydantic configuration
        """

        extra = Extra.allow
        use_enum_values = True


class RelationshipFiltersModel(BaseModel):
    """
    Validator model for relationship filters.
    """

    element_id: Optional[str] = Field(alias="$elementId")
    id: Optional[int] = Field(alias="$id")
    labels: Optional[Union[str, List[str]]] = Field(alias="$labels")

    normalize_and_validate_fields = root_validator(allow_reuse=True)(_normalize_fields)

    class Config:
        """
        Pydantic configuration
        """

        extra = Extra.allow
        use_enum_values = True
