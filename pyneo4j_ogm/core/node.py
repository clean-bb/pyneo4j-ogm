"""
This module holds the base node class `NodeModel` which is used to define database models for nodes.
It provides base functionality like de-/inflation and validation and methods for interacting with
the database for CRUD operations on nodes.
"""
import json
import re
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    ParamSpec,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from neo4j.graph import Node
from pydantic import BaseModel, PrivateAttr

from pyneo4j_ogm.core.base import ModelBase, hooks
from pyneo4j_ogm.exceptions import (
    InstanceDestroyed,
    InstanceNotHydrated,
    MissingFilters,
    NoResultsFound,
)
from pyneo4j_ogm.fields.settings import NodeModelSettings, RelationshipModelSettings
from pyneo4j_ogm.logger import logger
from pyneo4j_ogm.queries.types import MultiHopFilters, NodeFilters, QueryOptions

if TYPE_CHECKING:
    from pyneo4j_ogm.fields.relationship_property import RelationshipProperty
else:
    RelationshipProperty = object

P = ParamSpec("P")
T = TypeVar("T", bound="NodeModel")


def ensure_alive(func):
    """
    Decorator to ensure that the decorated method is only called on a alive instance.

    Args:
        func (Callable): The method to decorate.

    Raises:
        InstanceDestroyed: Raised if the instance is destroyed.
        InstanceNotHydrated: Raised if the instance is not hydrated.

    Returns:
        Callable: The decorated method.
    """

    @wraps(func)
    def wrapper(self, *args: Any, **kwargs: Any):
        if getattr(self, "_destroyed", False):
            raise InstanceDestroyed()

        if getattr(self, "_element_id", None) is None or getattr(self, "_id", None) is None:
            raise InstanceNotHydrated()

        return func(self, *args, **kwargs)

    return wrapper


class NodeModel(ModelBase[NodeModelSettings]):
    """
    Base model for all node models. Every node model should inherit from this class to define a
    model.
    """

    __settings__: NodeModelSettings
    _relationships_properties: Set[str] = PrivateAttr()
    Settings: ClassVar[Type[NodeModelSettings]]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Build relationship properties
        logger.debug("Building relationship properties for model %s", self.__class__.__name__)
        for property_name, property_value in self.__dict__.items():
            if hasattr(property_value, "_build_property"):
                cast(RelationshipProperty, property_value)._build_property(self, property_name)

    def __init_subclass__(cls) -> None:
        setattr(cls, "_relationships_properties", set())
        setattr(cls, "__settings__", NodeModelSettings())

        super().__init_subclass__()

        # Check if node labels is set, if not fall back to model name
        labels: Union[Set[str], None] = getattr(cls.__settings__, "labels", None)

        if labels is None or (labels is not None and len(labels) == 0):
            logger.info(
                "No labels have been defined for model %s, using model name as label",
                cls.__name__,
            )
            fallback_labels = re.findall(r"[A-Z][^A-Z]*", cls.__name__)
            setattr(cls.__settings__, "labels", set(fallback_labels))

        logger.debug("Collecting relationship properties for model %s", cls.__name__)
        for property_name, value in cls.__fields__.items():
            # Check if value is None here to prevent breaking logic if property_name is of type None
            if value.type_ is not None and hasattr(value.type_, "_build_property"):
                cls._relationships_properties.add(property_name)
                cls.__settings__.exclude_from_export.add(property_name)

    @hooks
    async def create(self: T) -> T:
        """
        Creates a new node from the current instance. After the method is finished, a newly created
        instance is seen as `alive` and any methods can be called on it.

        Raises:
            NoResultsFound: Raised if the query did not return the created node.

        Returns:
            T: The current model instance.
        """
        logger.info("Creating new node from model instance %s", self.__class__.__name__)
        deflated_properties = self._deflate()

        set_query = (
            f"SET {', '.join(f'n.{property_name} = ${property_name}' for property_name in deflated_properties.keys())}"
            if len(deflated_properties.keys()) != 0
            else ""
        )

        results, _ = await self._client.cypher(
            query=f"""
                CREATE {self._query_builder.node_match(list(self.__settings__.labels))}
                {set_query}
                RETURN n
            """,
            parameters=deflated_properties,
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        logger.debug("Hydrating instance values")
        setattr(self, "_element_id", getattr(cast(T, results[0][0]), "_element_id"))
        setattr(self, "_id", getattr(cast(T, results[0][0]), "_id"))

        logger.debug("Resetting modified properties")
        self._db_properties = self.dict()
        logger.info("Created new node %s", self)

        return self

    @hooks
    @ensure_alive
    async def update(self) -> None:
        """
        Updates the corresponding node in the database with the current instance values.

        Raises:
            NoResultsFound: Raised if the query did not return the updated node.
        """
        deflated = self._deflate()

        logger.info(
            "Updating node %s with current properties %s",
            self,
            deflated,
        )
        set_query = ", ".join(
            [
                f"n.{property_name} = ${property_name}"
                for property_name in deflated
                if property_name in self.modified_properties
            ]
        )

        results, _ = await self._client.cypher(
            query=f"""
                MATCH {self._query_builder.node_match(list(self.__settings__.labels))}
                WHERE elementId(n) = $element_id
                {f"SET {set_query}" if set_query != "" else ""}
                RETURN n
            """,
            parameters={"element_id": self._element_id, **deflated},
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        logger.debug("Resetting modified properties")
        self._db_properties = self.dict()
        logger.info("Updated node %s", self)

    @hooks
    @ensure_alive
    async def delete(self) -> None:
        """
        Deletes the corresponding node in the database and marks this instance as destroyed. If
        another method is called on this instance, an `InstanceDestroyed` will be raised.

        Raises:
            NoResultsFound: Raised if the query did not return the updated node.
        """
        logger.info("Deleting node %s", self)
        results, _ = await self._client.cypher(
            query=f"""
                MATCH {self._query_builder.node_match(list(self.__settings__.labels))}
                WHERE elementId(n) = $element_id
                DETACH DELETE n
                RETURN count(n)
            """,
            parameters={"element_id": self._element_id},
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        logger.debug("Marking instance as destroyed")
        setattr(self, "_destroyed", True)
        logger.info("Deleted node %s", self)

    @hooks
    @ensure_alive
    async def refresh(self) -> None:
        """
        Refreshes the current instance with the values from the database.

        Raises:
            NoResultsFound: Raised if the query did not return the current node.
        """
        logger.info("Refreshing node %s with values from database", self)
        results, _ = await self._client.cypher(
            query=f"""
                MATCH {self._query_builder.node_match(list(self.__settings__.labels))}
                WHERE elementId(n) = $element_id
                RETURN n
            """,
            parameters={"element_id": self._element_id},
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        logger.debug("Updating current instance")
        self.__dict__.update(results[0][0].__dict__)
        logger.info("Refreshed node %s", self)

    @hooks
    @ensure_alive
    async def find_connected_nodes(
        self: T,
        filters: MultiHopFilters,
        projections: Optional[Dict[str, str]] = None,
        options: Optional[QueryOptions] = None,
        auto_fetch_nodes: bool = False,
        auto_fetch_models: Optional[List[Union[str, Type["NodeModel"]]]] = None,
    ) -> List[Union[T, Dict[str, Any]]]:
        """
        Gets all connected nodes which match the provided `filters` parameter over multiple hops.

        Args:
            filters (MultiHopFilters): The filters to apply to the query.
            projections (Dict[str, str], optional): The properties to project from the node. The keys define
                the new keys in the projection and the value defines the model property to be projected. A invalid
                or empty projection will result in the whole model instance being returned. Defaults to None.
            options (QueryOptions, optional): The options to apply to the query. Defaults to None.
            auto_fetch_nodes (bool, optional): Whether to automatically fetch connected nodes. Takes priority over the
                identical option defined in `Settings`. Defaults to False.
            auto_fetch_models (List[Union[str, Type["NodeModel"]]], optional): A list of models to auto-fetch.
                `auto_fetch_nodes` has to be set to `True` for this to have any effect. Defaults to [].

        Returns:
            List[T | Dict[str, Any]]: The nodes matched by the query or dictionaries of the projected properties.
        """
        do_auto_fetch: bool = False
        match_queries, return_queries = [], []
        target_node_model: Optional[T] = None

        logger.info(
            "Getting connected nodes for node %s matching filters %s over multiple hops",
            self,
            filters,
        )
        self._query_builder.reset_query()
        if filters is not None:
            self._query_builder.multi_hop_filters(filters=filters)
        if options is not None:
            self._query_builder.query_options(options=options)
        if projections is not None:
            self._query_builder.build_projections(projections=projections, ref="m")

        projection_query = (
            "DISTINCT m" if self._query_builder.query["projections"] == "" else self._query_builder.query["projections"]
        )

        if auto_fetch_nodes:
            logger.debug("Auto-fetching nodes is enabled, checking if model with target labels is registered")

            labels: Optional[List[str]] = None

            if "$node" in filters and "$labels" in filters["$node"]:
                labels = cast(List[str], filters["$node"]["$labels"])

            for model in self._client.models:
                if hasattr(model.__settings__, "labels") and list(getattr(model.__settings__, "labels", [])) == labels:
                    target_node_model = cast(T, model)
                    break

            if target_node_model is None:
                logger.warning("No model with labels %s is registered, disabling auto-fetch", labels)
            else:
                logger.debug("Model with labels %s is registered, building auto-fetch query", labels)
                match_queries, return_queries = target_node_model._build_auto_fetch(  # pylint: disable=protected-access
                    ref="m", nodes_to_fetch=auto_fetch_models
                )

                do_auto_fetch = all(
                    [
                        auto_fetch_nodes or self.__settings__.auto_fetch_nodes,
                        len(match_queries) != 0,
                        len(return_queries) != 0,
                    ]
                )

        results, meta = await self._client.cypher(
            query=f"""
                MATCH {self._query_builder.node_match(list(self.__settings__.labels))}{self._query_builder.query['match']}
                WHERE
                    elementId(n) = $element_id
                    {f"AND {self._query_builder.query['where']}" if self._query_builder.query['where'] != "" else ""}
                WITH m
                {self._query_builder.query['options']}
                {" ".join(f"OPTIONAL MATCH {match_query}" for match_query in match_queries) if do_auto_fetch else ""}
                RETURN {projection_query}{f', {", ".join(return_queries)}' if do_auto_fetch else ''}
            """,
            parameters={
                "element_id": self._element_id,
                **self._query_builder.parameters,
            },
        )

        instances: List[Union[T, Dict[str, Any]]] = []

        logger.debug("Building instances from results")
        if do_auto_fetch:
            # Add auto-fetched nodes to relationship properties
            added_nodes: Set[str] = set()

            logger.debug("Adding auto-fetched nodes to relationship properties")
            for result_list in results:
                for index, result in enumerate(result_list):
                    if result is None or result_list[0] is None:
                        continue

                    instance_element_id = getattr(result, "_element_id")
                    if instance_element_id in added_nodes:
                        continue

                    if index == 0 and target_node_model is not None:
                        instances.append(
                            target_node_model._inflate(node=result) if isinstance(result, Node) else result
                        )
                    else:
                        target_instance = [
                            instance
                            for instance in instances
                            if getattr(result_list[0], "_element_id") == getattr(instance, "_element_id")
                        ][0]
                        relationship_property = getattr(target_instance, meta[index])
                        nodes = cast(List[str], getattr(relationship_property, "_nodes"))
                        nodes.append(result)

                    added_nodes.add(instance_element_id)
        else:
            for result_list in results:
                for result in result_list:
                    if result is None:
                        continue

                    if isinstance(result, Node):
                        instances.append(self._inflate(node=result))
                    elif isinstance(result, list):
                        instances.extend(result)
                    else:
                        instances.append(result)

        return instances

    @classmethod
    @hooks
    async def find_one(
        cls: Type[T],
        filters: NodeFilters,
        projections: Optional[Dict[str, str]] = None,
        auto_fetch_nodes: bool = False,
        auto_fetch_models: Optional[List[Union[str, Type["NodeModel"]]]] = None,
    ) -> Optional[Union[T, Dict[str, Any]]]:
        """
        Finds the first node that matches `filters` and returns it. If no matching node is found,
        `None` is returned instead.

        Args:
            filters (NodeFilters): The filters to apply to the query.
            projections (Dict[str, str], optional): The properties to project from the node. The keys define
                the new keys in the projection and the value defines the model property to be projected. A invalid
                or empty projection will result in the whole model instance being returned. Defaults to None.
            auto_fetch_nodes (bool, optional): Whether to automatically fetch connected nodes. Takes priority over the
                identical option defined in `Settings`. Can not be used with projections. Defaults to False.
            auto_fetch_models (List[Union[str, Type["NodeModel"]]], optional): A list of models to auto-fetch.
                `auto_fetch_nodes` has to be set to `True` for this to have any effect. Defaults to [].

        Raises:
            MissingFilters: Raised if no filters or invalid filters are provided.

        Returns:
            T | Dict[str, Any] | None: A instance of the model or None if no match is found or a dictionary of the
                projected properties.
        """
        logger.info(
            "Getting first encountered node of model %s matching filters %s",
            cls.__name__,
            filters,
        )
        cls._query_builder.reset_query()
        cls._query_builder.node_filters(filters=filters)

        if projections is not None:
            cls._query_builder.build_projections(projections=projections)

        match_queries, return_queries = cls._build_auto_fetch(nodes_to_fetch=auto_fetch_models)
        projection_query = (
            "DISTINCT n" if cls._query_builder.query["projections"] == "" else cls._query_builder.query["projections"]
        )

        if cls._query_builder.query["where"] == "":
            raise MissingFilters()

        do_auto_fetch = all(
            [
                projections is None,
                auto_fetch_nodes or cls.__settings__.auto_fetch_nodes,
                len(match_queries) != 0,
                len(return_queries) != 0,
                cls._query_builder.query["projections"] == "",
            ]
        )

        if do_auto_fetch:
            logger.debug("Querying database with auto-fetch")
            results, meta = await cls._client.cypher(
                query=f"""
                    MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                    WHERE {cls._query_builder.query['where']}
                    WITH n
                    LIMIT 1
                    {" ".join(f"OPTIONAL MATCH {match_query}" for match_query in match_queries)}
                    RETURN {projection_query}, {', '.join(return_queries)}
                """,
                parameters=cls._query_builder.parameters,
            )
        else:
            logger.debug("Querying database without auto-fetch")
            results, meta = await cls._client.cypher(
                query=f"""
                    MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                    WHERE {cls._query_builder.query['where']}
                    RETURN {projection_query}
                    LIMIT 1
                """,
                parameters=cls._query_builder.parameters,
            )

        logger.debug("Checking if query returned a result")
        if (
            len(results) == 0
            or len(results[0]) == 0
            or results[0][0] is None
            or (isinstance(results[0][0], dict) and len(results[0][0]) == 0)
        ):
            return None

        logger.debug("Checking if node has to be parsed to instance")
        if isinstance(results[0][0], Node):
            instance = cls._inflate(node=results[0][0])
        elif isinstance(results[0][0], list):
            instance = results[0][0][0]
        else:
            instance = results[0][0]

        if not do_auto_fetch:
            return instance

        # Add auto-fetched nodes to relationship properties
        added_nodes: Set[str] = set()

        logger.debug("Adding auto-fetched nodes to relationship properties")
        for result_list in results:
            for index, result in enumerate(result_list[1:]):
                if result is not None:
                    relationship_property = getattr(instance, meta[index + 1])
                    nodes = cast(List[str], getattr(relationship_property, "_nodes"))
                    element_id = getattr(result, "_element_id")

                    if element_id not in added_nodes:
                        # Add model instance to nodes list and mark it as added
                        nodes.append(result)
                        added_nodes.add(element_id)

        return instance

    @classmethod
    @hooks
    async def find_many(
        cls: Type[T],
        filters: Optional[NodeFilters] = None,
        projections: Optional[Dict[str, str]] = None,
        options: Optional[QueryOptions] = None,
        auto_fetch_nodes: bool = False,
        auto_fetch_models: Optional[List[Union[str, Type["NodeModel"]]]] = None,
    ) -> List[Union[T, Dict[str, Any]]]:
        """
        Finds the all nodes that matches `filters` and returns them. If no matches are found, an
        empty list is returned instead.

        Args:
            filters (NodeFilters, optional): The filters to apply to the query. Defaults to None.
            projections (Dict[str, str], optional): The properties to project from the node. The keys define
                the new keys in the projection and the value defines the model property to be projected. A invalid
                or empty projection will result in the whole model instance being returned. Defaults to None.
            options (QueryOptions, optional): The options to apply to the query. Defaults to None.
            auto_fetch_nodes (bool, optional): Whether to automatically fetch connected nodes. Takes priority over the
                identical option defined in `Settings`. Defaults to False.
            auto_fetch_models (List[Union[str, Type["NodeModel"]]], optional): A list of models to auto-fetch.
                `auto_fetch_nodes` has to be set to `True` for this to have any effect. Defaults to [].

        Returns:
            List[T | Dict[str, Any]]: A list of model instances or dictionaries of the projected properties.
        """
        logger.info("Getting nodes of model %s matching filters %s", cls.__name__, filters)
        match_queries, return_queries = cls._build_auto_fetch(nodes_to_fetch=auto_fetch_models)
        cls._query_builder.reset_query()
        if filters is not None:
            cls._query_builder.node_filters(filters=filters)
        if options is not None:
            cls._query_builder.query_options(options=options)
        if projections is not None:
            cls._query_builder.build_projections(projections=projections)

        instances: List[Union[T, Dict[str, Any]]] = []
        projection_query = (
            "DISTINCT n" if cls._query_builder.query["projections"] == "" else cls._query_builder.query["projections"]
        )

        do_auto_fetch = all(
            [
                projections is None,
                auto_fetch_nodes or cls.__settings__.auto_fetch_nodes,
                len(match_queries) != 0,
                len(return_queries) != 0,
                cls._query_builder.query["projections"] == "",
            ]
        )

        if do_auto_fetch:
            logger.debug("Querying database with auto-fetch")
            results, meta = await cls._client.cypher(
                query=f"""
                    MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                    {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                    WITH n
                    {cls._query_builder.query['options']}
                    {" ".join(f"OPTIONAL MATCH {match_query}" for match_query in match_queries)}
                    RETURN {projection_query}, {', '.join(return_queries)}
                """,
                parameters=cls._query_builder.parameters,
            )

            # Add auto-fetched nodes to relationship properties
            added_nodes: Set[str] = set()

            logger.debug("Adding auto-fetched nodes to relationship properties")
            for result_list in results:
                for index, result in enumerate(result_list):
                    if result is None or result_list[0] is None:
                        continue

                    instance_element_id = getattr(result, "_element_id")
                    if instance_element_id in added_nodes:
                        continue

                    if index == 0:
                        instances.append(cls._inflate(node=result) if isinstance(result, Node) else result)
                    else:
                        target_instance = [
                            instance
                            for instance in instances
                            if getattr(result_list[0], "_element_id") == getattr(instance, "_element_id")
                        ][0]
                        relationship_property = getattr(target_instance, meta[index])
                        nodes = cast(List[str], getattr(relationship_property, "_nodes"))
                        nodes.append(result)

                    added_nodes.add(instance_element_id)

            return instances
        else:
            logger.debug("Querying database without auto-fetch")
            results, _ = await cls._client.cypher(
                query=f"""
                    MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                    {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                    RETURN {projection_query}
                    {cls._query_builder.query['options']}
                """,
                parameters=cls._query_builder.parameters,
            )

            for result_list in results:
                for result in result_list:
                    if result is None:
                        continue

                    if isinstance(result, Node):
                        instances.append(cls._inflate(node=result))
                    elif isinstance(result, list):
                        instances.extend(result)
                    else:
                        instances.append(result)

            return instances

    @classmethod
    @hooks
    async def update_one(cls: Type[T], update: Dict[str, Any], filters: NodeFilters, new: bool = False) -> Optional[T]:
        """
        Finds the first node that matches `filters` and updates it with the values defined by
        `update`. If no match is found, `None` is returned instead.

        Args:
            update (Dict[str, Any]): Values to update the node properties with.
            filters (NodeFilters): The filters to apply to the query.
            new (bool, optional): Whether to return the updated node. By default, the old node is
                returned. Defaults to False.

        Raises:
            MissingFilters: Raised if no filters or invalid filters are provided.

        Returns:
            T | None: By default, the old node instance is returned. If `new` is set to `True`, the result
                will be the `updated` instance.
        """
        new_instance: T

        logger.info(
            "Updating first encountered node of model %s matching filters %s",
            cls.__name__,
            filters,
        )
        logger.debug(
            "Getting first encountered node of model %s matching filters %s",
            cls.__name__,
            filters,
        )
        cls._query_builder.reset_query()
        cls._query_builder.node_filters(filters=filters)

        if cls._query_builder.query["where"] == "":
            raise MissingFilters()

        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                WHERE {cls._query_builder.query['where']}
                RETURN DISTINCT n
                LIMIT 1
            """,
            parameters=cls._query_builder.parameters,
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            return None
        old_instance = results[0][0]

        # Update existing instance with values and save
        logger.debug("Creating instance copy with new values %s", update)
        new_instance = cls(**cast(T, old_instance).dict())

        for key, value in update.items():
            if key in cls.__fields__:
                setattr(new_instance, key, value)
        setattr(new_instance, "_element_id", getattr(old_instance, "_element_id", None))

        deflated = new_instance._deflate()
        set_query = ", ".join(
            [
                f"n.{property_name} = ${property_name}"
                for property_name in deflated
                if property_name in new_instance.modified_properties
            ]
        )

        await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(new_instance.__settings__.labels))}
                WHERE elementId(n) = $element_id
                {f"SET {set_query}" if set_query != "" else ""}
            """,
            parameters={"element_id": new_instance._element_id, **deflated},
        )
        logger.info("Successfully updated node %s", getattr(new_instance, "_element_id"))

        if new:
            return new_instance

        return old_instance

    @classmethod
    @hooks
    async def update_many(
        cls: Type[T],
        update: Dict[str, Any],
        filters: Optional[NodeFilters] = None,
        new: bool = False,
    ) -> List[T]:
        """
        Finds all nodes that match `filters` and updates them with the values defined by `update`.

        Args:
            update (Dict[str, Any]): Values to update the node properties with.
            filters (NodeFilters, optional): The filters to apply to the query. Defaults to None.
            new (bool, optional): Whether to return the updated nodes. By default, the old nodes
                is returned. Defaults to False.

        Returns:
            List[T]: By default, the old node instances are returned. If `new` is set to `True`,
                the result will be the `updated/created instances`.
        """
        new_instance: T

        logger.info("Updating all nodes of model %s matching filters %s", cls.__name__, filters)
        cls._query_builder.reset_query()
        if filters is not None:
            cls._query_builder.node_filters(filters=filters)

        logger.debug("Getting all nodes of model %s matching filters %s", cls.__name__, filters)
        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                RETURN DISTINCT n
            """,
            parameters=cls._query_builder.parameters,
        )

        old_instances: List[T] = []

        for result_list in results:
            for result in result_list:
                if result is None:
                    continue

                old_instances.append(cls._inflate(node=result) if isinstance(result, Node) else result)

        logger.debug("Checking if query returned a result")
        if len(old_instances) == 0:
            logger.debug("No results found")
            return []

        # Try and parse update values into random instance to check validation
        logger.debug("Creating instance copy with new values %s", update)
        new_instance = cls(**old_instances[0].dict())
        for key, value in update.items():
            if key in cls.__fields__:
                setattr(new_instance, key, value)

        deflated_properties = new_instance._deflate()

        # Update instances
        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                SET {", ".join([f"n.{property_name} = ${property_name}" for property_name in deflated_properties if property_name in update])}
                RETURN DISTINCT n
            """,
            parameters={**deflated_properties, **cls._query_builder.parameters},
        )

        logger.info(
            "Successfully updated %s nodes %s",
            len(old_instances),
            [getattr(instance, "_element_id") for instance in old_instances],
        )
        logger.debug("Building instances from results")
        if new:
            instances: List[T] = []

            for result_list in results:
                for result in result_list:
                    if result is not None:
                        instances.append(result)
            return instances
        return old_instances

    @classmethod
    @hooks
    async def delete_one(cls: Type[T], filters: NodeFilters) -> int:
        """
        Finds the first node that matches `filters` and deletes it. If no match is found, a
        `NoResultsFound` is raised.

        Args:
            filters (NodeFilters): The filters to apply to the query.

        Raises:
            NoResultsFound: Raised if the query did not return the node.
            MissingFilters: Raised if no filters or invalid filters are provided.

        Returns:
            int: The number of deleted nodes.
        """
        logger.info(
            "Deleting first encountered node of model %s matching filters %s",
            cls.__name__,
            filters,
        )
        cls._query_builder.reset_query()
        cls._query_builder.node_filters(filters=filters)

        if cls._query_builder.query["where"] == "":
            raise MissingFilters()

        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                WHERE {cls._query_builder.query['where']}
                WITH n LIMIT 1
                DETACH DELETE n
                RETURN DISTINCT n
            """,
            parameters=cls._query_builder.parameters,
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        logger.info("Deleted node %s", cast(Node, results[0][0]).element_id)
        return len(results)

    @classmethod
    @hooks
    async def delete_many(cls: Type[T], filters: Optional[NodeFilters] = None) -> int:
        """
        Finds all nodes that match `filters` and deletes them.

        Args:
            filters (NodeFilters, optional): The filters to apply to the query. Defaults to None.

        Returns:
            int: The number of deleted nodes.
        """
        logger.info("Deleting all nodes of model %s matching filters %s", cls.__name__, filters)
        cls._query_builder.reset_query()
        if filters is not None:
            cls._query_builder.node_filters(filters=filters)

        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                DETACH DELETE n
                RETURN DISTINCT n
            """,
            parameters=cls._query_builder.parameters,
        )

        logger.info("Deleted %s nodes", len(results))
        return len(results)

    @classmethod
    @hooks
    async def count(cls: Type[T], filters: Optional[NodeFilters] = None) -> int:
        """
        Counts all nodes which match the provided `filters` parameter.

        Args:
            filters (NodeFilters, optional): The filters to apply to the query. Defaults to None.

        Returns:
            int: The number of nodes matched by the query.
        """
        logger.info(
            "Getting count of nodes of model %s matching filters %s",
            cls.__name__,
            filters,
        )
        cls._query_builder.reset_query()
        if filters is not None:
            cls._query_builder.node_filters(filters=filters)

        results, _ = await cls._client.cypher(
            query=f"""
                MATCH {cls._query_builder.node_match(list(cls.__settings__.labels))}
                {f"WHERE {cls._query_builder.query['where']}" if cls._query_builder.query['where'] != "" else ""}
                RETURN count(n)
            """,
            parameters=cls._query_builder.parameters,
        )

        logger.debug("Checking if query returned a result")
        if len(results) == 0 or len(results[0]) == 0 or results[0][0] is None:
            raise NoResultsFound()

        return results[0][0]

    def _deflate(self) -> Dict[str, Any]:
        """
        Deflates the current model instance into a python dictionary which can be stored in Neo4j.

        Returns:
            Dict[str, Any]: The deflated model instance.
        """
        logger.debug("Deflating model %s to storable dictionary", self)
        deflated: Dict[str, Any] = json.loads(self.json(exclude={*self._relationships_properties, "__settings__"}))

        # Serialize nested BaseModel or dict instances to JSON strings
        for key, value in deflated.items():
            if isinstance(value, (dict, BaseModel)):
                deflated[key] = json.dumps(value)
            if isinstance(value, list):
                deflated[key] = [json.dumps(item) if isinstance(item, (dict, BaseModel)) else item for item in value]

        return deflated

    @classmethod
    def _inflate(cls: Type[T], node: Node) -> T:
        """
        Inflates a node instance into a instance of the current model.

        Args:
            node (Node): Node to inflate.

        Raises:
            InflationFailure: Raised if inflating the node fails.

        Returns:
            T: A new instance of the current model with the properties from the node instance.
        """
        inflated: Dict[str, Any] = {}

        def try_property_parsing(property_value: str) -> Union[str, Dict[str, Any], BaseModel]:
            try:
                return json.loads(property_value)
            except:
                return property_value

        logger.debug("Inflating node %s to model instance", node)
        for node_property in node.items():
            property_name, property_value = node_property

            if isinstance(property_value, str):
                inflated[property_name] = try_property_parsing(property_value)
            elif isinstance(property_value, list):
                inflated[property_name] = [try_property_parsing(item) for item in property_value]
            else:
                inflated[property_name] = property_value

        instance = cls(**inflated)
        setattr(instance, "_element_id", node._element_id)
        setattr(instance, "_id", node._id)
        return instance

    @classmethod
    def _build_auto_fetch(
        cls, nodes_to_fetch: Optional[List[Union[str, Type["NodeModel"]]]] = None, ref: str = "n"
    ) -> Tuple[List[str], List[str]]:
        """
        Builds the auto-fetch query for the instance.

        Args:
            nodes_to_fetch (List[Union[str, Type["NodeModel"]]] | None): The nodes to fetch. Can contain the actual
                Model of the Node or the model name as a string. If None, all nodes will be fetched. Defaults to None.
            ref (str, optional): The reference to use for the node. Defaults to "n".

        Returns:
            Tuple[List[str], List[str]]: The `MATCH` and `RETURN` queries.
        """
        match_queries: List[str] = []
        return_queries: List[str] = []
        node_model_names: List[str] = []

        if nodes_to_fetch is not None:
            for node in nodes_to_fetch:
                if isinstance(node, str):
                    node_model_names.append(node)
                else:
                    node_model_names.append(node.__name__)

        logger.debug("Building node match queries for auto-fetch")
        for defined_relationship in cls._relationships_properties:
            relationship_type: Optional[str] = None
            end_node_labels: Optional[List[str]] = None
            relationship_property = cast(RelationshipProperty, cls.__fields__[defined_relationship].default)
            direction = getattr(relationship_property, "_direction")

            if (
                nodes_to_fetch is not None
                and getattr(relationship_property, "_target_model_name") not in node_model_names
            ):
                continue

            for model in cls._client.models:
                if model.__name__ == getattr(relationship_property, "_relationship_model_name", None):
                    relationship_type = cast(RelationshipModelSettings, model.__settings__).type
                elif model.__name__ == getattr(relationship_property, "_target_model_name", None):
                    end_node_labels = list(cast(NodeModelSettings, model.__settings__).labels)

            if relationship_type is None:
                logger.debug(
                    "Model for relationship used on property %s was not registered, skipping", defined_relationship
                )
                continue
            if end_node_labels is None:
                logger.debug(
                    "Model for target node used on property %s was not registered, skipping", defined_relationship
                )
                continue

            return_queries.append(defined_relationship)
            match_queries.append(
                cls._query_builder.relationship_match(
                    ref=None,
                    type_=relationship_type,
                    start_node_ref=ref,
                    direction=direction,
                    end_node_ref=defined_relationship,
                    end_node_labels=end_node_labels,
                )
            )

        return match_queries, return_queries
