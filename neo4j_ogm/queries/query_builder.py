from copy import deepcopy
from typing import Any

from neo4j_ogm.exceptions import InvalidOperator
from neo4j_ogm.queries.validators import (
    ComparisonExpressionValidator,
    ExpressionsValidator,
    LogicalExpressionValidator,
    Neo4jExpressionValidator,
)


class QueryBuilder:
    """
    Builder class for generating queries from expressions.
    """

    __comparison_operators: dict[str, str] = {}
    __logical_operators: dict[str, str] = {}
    __neo4j_operators: dict[str, str] = {}
    _variable_name_overwrite: str | None = None
    _parameter_count: int = 0
    property_name: str
    ref: str

    def __init__(self) -> None:
        # Get operators and parsing format
        for _, field in ComparisonExpressionValidator.__fields__.items():
            self.__comparison_operators[field.alias] = field.field_info.extra["extra"]["parser"]

        for _, field in LogicalExpressionValidator.__fields__.items():
            self.__logical_operators[field.alias] = field.field_info.extra["extra"]["parser"]

        for _, field in Neo4jExpressionValidator.__fields__.items():
            self.__neo4j_operators[field.alias] = field.field_info.extra["extra"]["parser"]

    def build_property_expression(self, expressions: dict[str, Any], ref: str = "n") -> tuple[str, dict[str, Any]]:
        """
        Builds a query for filtering properties with the given operators.

        Args:
            expressions (dict[str, Any]): The expressions defining the operators.
            ref (str, optional): The variable to use inside the generated query. Defaults to "n".

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        normalized_expressions = self._validate_expressions(expressions=expressions)
        self.ref = ref

        return self._build_nested_expressions(normalized_expressions)

    def _build_nested_expressions(self, expressions: dict[str, Any], level: int = 0) -> tuple[str, dict[str, Any]]:
        """
        Builds nested operators defined in provided expressions.

        Args:
            expressions (dict[str, Any]): The expressions to build the query from.
            level (int, optional): The recursion depth level. Should not be modified outside the function itself.
                Defaults to 0.

        Raises:
            InvalidOperator: If the `expressions` parameter is not a valid dict.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        complete_parameters: dict[str, Any] = {}
        partial_queries: list[str] = []

        if not isinstance(expressions, dict):
            raise InvalidOperator(f"Expressions must be instance of dict, got {type(expressions)}")

        for property_or_operator, expression_or_value in expressions.items():
            parameters = {}
            query = ""

            if not property_or_operator.startswith("$"):
                # Update current property name if the key is not a operator
                self.property_name = property_or_operator

            if level == 0 and property_or_operator.startswith("$"):
                query, parameters = self._build_neo4j_operator(property_or_operator, expression_or_value)
            elif property_or_operator == "$not":
                query, parameters = self._build_not_operator(expression=expression_or_value)
            elif property_or_operator == "$size":
                query, parameters = self._build_size_operator(expression=expression_or_value)
            elif property_or_operator == "$all":
                query, parameters = self._build_all_operator(expressions=expression_or_value)
            elif property_or_operator == "$exists":
                query = self._build_exists_operator(exists=expression_or_value)
            elif property_or_operator in self.__comparison_operators:
                query, parameters = self._build_comparison_operator(
                    operator=property_or_operator, value=expression_or_value
                )
            elif property_or_operator in self.__logical_operators:
                query, parameters = self._build_logical_operator(
                    operator=property_or_operator, expressions=expression_or_value
                )
            elif not property_or_operator.startswith("$"):
                query, parameters = self._build_nested_expressions(expressions=expression_or_value, level=level + 1)

            partial_queries.append(query)
            complete_parameters = {**complete_parameters, **parameters}

        complete_query = " AND ".join(partial_queries)
        return complete_query, complete_parameters

    def _build_comparison_operator(self, operator: str, value: Any) -> tuple[str, dict[str, Any]]:
        """
        Builds comparison operators.

        Args:
            operator (str): The operator to build.
            value (Any): The provided value for the operator.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        parameter_name = self._get_parameter_name()
        parameters = {}

        query = self.__comparison_operators[operator].format(
            property_name=self._get_variable_name(),
            value=f"${parameter_name}",
        )
        parameters[parameter_name] = value

        return query, parameters

    def _build_exists_operator(self, exists: bool) -> str:
        """
        Builds a `IS NOT NULL` or `IS NULL` query based on the defined value.

        Args:
            exists (bool): Whether the query should check if the property exists or not.

        Raises:
            InvalidOperator: If the operator value is not a bool.

        Returns:
            str: The generated query.
        """
        if not isinstance(exists, bool):
            raise InvalidOperator(f"$exists operator value must be a instance of bool, got {type(exists)}")

        query = "IS NULL" if exists is False else "IS NOT NULL"
        return query

    def _build_not_operator(self, expression: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """
        Builds a `NOT()` clause with the defined expressions.

        Args:
            expression (dict[str, Any]): The expressions defined for the `$not` operator.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        expression, complete_parameters = self._build_nested_expressions(expressions=expression, level=1)

        complete_query = f"NOT({expression})"
        return complete_query, complete_parameters

    def _build_size_operator(self, expression: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """
        Builds a `SIZE()` clause with the defined comparison operator.

        Args:
            expression (dict[str, Any]): The expression defined fot the `$size` operator.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        comparison_operator = next(iter(expression))
        self._variable_name_overwrite = f"SIZE({self._get_variable_name()})"

        query, parameters = self._build_comparison_operator(
            operator=comparison_operator, value=expression[comparison_operator]
        )

        self._variable_name_overwrite = None

        return query, parameters

    def _build_all_operator(self, expressions: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        """
        Builds a `ALL()` clause with the defined expressions.

        Args:
            expressions (list[dict[str, Any]]): Expressions to apply inside the `$all` operator.

        Raises:
            InvalidOperator: If the operator value is not a list.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        self._variable_name_overwrite = "i"
        complete_parameters: dict[str, Any] = {}
        partial_queries: list[str] = []

        if not isinstance(expressions, list):
            raise InvalidOperator(f"Value of $all operator must be list, got {type(expressions)}")

        for expression in expressions:
            query, parameters = self._build_nested_expressions(expressions=expression, level=1)

            partial_queries.append(query)
            complete_parameters = {
                **complete_parameters,
                **parameters,
            }

        self._variable_name_overwrite = None

        complete_query = f"ALL(i IN {self._get_variable_name()} WHERE {' AND '.join(partial_queries)})"
        return complete_query, complete_parameters

    def _build_logical_operator(self, operator: str, expressions: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        """
        Builds all expressions defined inside a logical operator.

        Args:
            operator (str): The logical operator.
            expressions (list[dict[str, Any]]): The expressions chained together by the operator.

        Raises:
            InvalidOperator: If the operator value is not a list.

        Returns:
            tuple[str, dict[str, Any]]: The query and parameters.
        """
        complete_parameters: dict[str, Any] = {}
        partial_queries: list[str] = []

        if not isinstance(expressions, list):
            raise InvalidOperator(f"Value of {operator} operator must be list, got {type(expressions)}")

        for expression in expressions:
            nested_query, parameters = self._build_nested_expressions(expressions=expression, level=1)

            partial_queries.append(nested_query)
            complete_parameters = {**complete_parameters, **parameters}

        complete_query = f"({f' {self.__logical_operators[operator]} '.join(partial_queries)})"
        return complete_query, complete_parameters

    def _build_neo4j_operator(self, operator: str, value: Any) -> tuple[str, dict[str, Any]]:
        """
        Builds operators for Neo4j-specific `elementId()` and `ID()`.

        Args:
            operator (str): The operator to build.
            value (Any): The value to use for building the operator.

        Returns:
            tuple[str, dict[str, Any]]: The generated query and parameters.
        """
        variable_name = self._get_parameter_name()

        query = self.__neo4j_operators[operator].format(ref=self.ref, value=variable_name)
        parameters = {variable_name: value}

        return query, parameters

    def _get_parameter_name(self) -> str:
        """
        Builds the parameter name and increment the parameter count by one.

        Returns:
            str: The generated parameter name.
        """
        parameter_name = f"{self.ref}_{self._parameter_count}"
        self._parameter_count += 1

        return parameter_name

    def _get_variable_name(self) -> str:
        """
        Builds the variable name used in the query.

        Returns:
            str: The generated variable name.
        """
        if self._variable_name_overwrite:
            return self._variable_name_overwrite

        return f"{self.ref}.{self.property_name}"

    def _normalize_expressions(self, expressions: dict[str, Any], level: int = 0) -> dict[str, Any]:
        """
        Normalizes and formats the provided expressions into usable expressions for the builder.

        Args:
            expressions (dict[str, Any]): The expressions to normalize
            level (int, optional): The recursion depth level. Should not be modified outside the function itself.
                Defaults to 0.

        Returns:
            dict[str, Any]: The normalized expressions.
        """
        normalized: dict[str, Any] = deepcopy(expressions)

        if isinstance(normalized, dict):
            # Transform values without a operator to a `$eq` operator
            for operator, value in normalized.items():
                if not isinstance(value, dict) and not isinstance(value, list):
                    # If the operator is a `$not` operator or just a property name, add a `$eq` operator
                    if operator in ["$not", "$size"] or not operator.startswith("$"):
                        normalized[operator] = {"$eq": value}

            if len(normalized.keys()) > 1 and level > 0:
                # If more than one operator is defined in a dict, transform operators to `$and` operator
                normalized = {"$and": [{operator: expression} for operator, expression in normalized.items()]}

        # Normalize nested operators
        if isinstance(normalized, list):
            for index, expression in enumerate(normalized):
                normalized[index] = self._normalize_expressions(expression, level + 1)
        elif isinstance(normalized, dict) and ("$query" not in normalized and "$parameters" not in normalized):
            for operator, expression in normalized.items():
                normalized[operator] = self._normalize_expressions(expression, level + 1)

        return normalized

    def _validate_expressions(self, expressions: dict[str, Any]) -> dict[str, Any]:
        """
        Validates given expressions.

        Args:
            expressions (dict[str, Any]): The expressions to validate.

        Returns:
            dict[str, Any]: The validated expressions.
        """
        validated_expressions: dict[str, Any] = {}

        for operator_or_property, value_or_expression in self._normalize_expressions(expressions=expressions).items():
            if operator_or_property.startswith("$") and operator_or_property in self.__neo4j_operators.items():
                # Handle neo4j operators
                validated = ExpressionsValidator.parse_obj({operator_or_property: value_or_expression})
                validated_expressions[operator_or_property] = validated.dict(by_alias=True, exclude_none=True)[
                    operator_or_property
                ]
            else:
                validated = ExpressionsValidator.parse_obj(value_or_expression)
                validated_expressions[operator_or_property] = validated.dict(by_alias=True, exclude_none=True)

        # Remove empty objects which remained from pydantic validation
        self._remove_invalid_expressions(validated_expressions)

        return validated_expressions

    def _remove_invalid_expressions(self, expressions: dict[str, Any], level: int = 0) -> None:
        """
        Recursively removes empty objects and nested fields which do not start with a `$` and are not top level keys
        from nested dictionaries and lists.

        Args:
            expressions (dict[str, Any]): The expression to check.
            level (int, optional): The recursion depth level. Should not be modified outside the function itself.
                Defaults to 0.
        """
        operators_to_remove: list[str] = []

        if not isinstance(expressions, dict):
            return

        for operator, expression in expressions.items():
            if isinstance(expression, dict):
                # Search through all operators nested within
                self._remove_invalid_expressions(expressions=expression, level=level + 1)

                if not expression:
                    operators_to_remove.append(operator)
            elif isinstance(expression, list):
                # Handle logical operators
                indexes_to_remove: list[str] = []

                for index, nested_expression in enumerate(expression):
                    # Search through all operators nested within
                    self._remove_invalid_expressions(expressions=nested_expression, level=level + 1)

                    if not nested_expression:
                        indexes_to_remove.append(index)

                # Remove all invalid indexes
                for index in indexes_to_remove:
                    expression.pop(index)
            elif not operator.startswith("$") and level != 0:
                operators_to_remove.append(operator)

        for operator in operators_to_remove:
            expressions.pop(operator)
