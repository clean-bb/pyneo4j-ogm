"""
Module containing all exceptions raised by the library.
"""


from typing import List


class Neo4jOGMException(Exception):
    """
    Base exception for all Neo4jOGM exceptions
    """


class NotConnectedToDatabase(Neo4jOGMException):
    """
    Exception which gets raised if the client tries to operate on a database without a valid.
    connection.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Client is not connected to a database", *args)


class MissingDatabaseURI(Neo4jOGMException):
    """
    Exception which gets raised if the client is initialized without providing a connection.
    URI
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Trying to initialize client without providing connection URI", *args)


class InvalidEntityType(Neo4jOGMException):
    """
    Exception which gets raised if the client provides a invalid entity type
    """

    def __init__(self, available_types: List[str], entity_type: str, *args: object) -> None:
        super().__init__(
            f"Invalid entity type. Expected entity type to be one of {available_types}, got {entity_type}",
            *args,
        )


class InvalidIndexType(Neo4jOGMException):
    """
    Exception which gets raised if the client provides a invalid index type when creating a new
    index.
    """

    def __init__(self, available_types: List[str], index_type: str, *args: object) -> None:
        super().__init__(
            f"Invalid index type. Expected index to be one of {available_types}, got {index_type}",
            *args,
        )


class InstanceNotHydrated(Neo4jOGMException):
    """
    Exception which gets raised when a query is run with a instance which has not been hydrated yet.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Queries can not be run on instances which have not been hydrated", *args)


class InstanceDestroyed(Neo4jOGMException):
    """
    Exception which gets raised when a query is run with a instance which has been destroyed.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Queries can not be run on instances which have been destroyed", *args)


class NoResultsFound(Neo4jOGMException):
    """
    Exception which gets raised when a query returns no result.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("The query was expected to return a result, but did not", *args)


class UnregisteredModel(Neo4jOGMException):
    """
    Exception which gets raised when a model, which has not been registered, gets used.
    """

    def __init__(self, unregistered_model: str, *args: object) -> None:
        super().__init__(
            f"Model {unregistered_model} was not registered, but another model is using it",
            *args,
        )


class InvalidTargetNode(Neo4jOGMException):
    """
    Exception which gets raised when a relationship property receives a target node of the wrong
    model type.
    """

    def __init__(self, expected_type: str, actual_type: str, *args: object) -> None:
        super().__init__(
            f"Expected target node to be of type {expected_type}, but got {actual_type}",
            *args,
        )


class InvalidLabelOrType(Neo4jOGMException):
    """
    Exception which gets raised when invalid labels or a invalid type are passed to a method.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Invalid label or type", *args)


class TransactionInProgress(Neo4jOGMException):
    """
    Exception which gets raised when a transaction is in progress, but another one is started.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("A transaction is already in progress.", *args)


class NotConnectedToSourceNode(Neo4jOGMException):
    """
    Exception which gets raised when a node is to be replaced by another, but the node is not
    connected to the source node.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Node not connected to source node.", *args)


class MissingFilters(Neo4jOGMException):
    """
    Exception which gets raised when a filter is required, but none or a invalid one is provided.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(
            "Missing or invalid filters. Maybe you got a typo in the query operators?",
            *args,
        )


class ModelImportFailure(Neo4jOGMException):
    """
    Exception which gets raised when a model dict is imported, but does not have a element_id key.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Missing 'element_id' key in model dict.", *args)


class ReservedPropertyName(Neo4jOGMException):
    """
    Exception which gets raised when a model defined a property name which is reserved.
    """

    def __init__(self, property_name: str, *args: object) -> None:
        super().__init__(f"{property_name} is reserved for internal use.", *args)


class InvalidRelationshipHops(Neo4jOGMException):
    """
    Exception which gets raised when a relationship hop is invalid.
    """

    def __init__(self, *args: object) -> None:
        super().__init__("Invalid relationship hop. Hop must be positive integer or '*'.", *args)
