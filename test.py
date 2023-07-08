import asyncio
import random
from copy import deepcopy
from typing import Any, Dict, Generic, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from neo4j_ogm.core.client import Neo4jClient
from neo4j_ogm.core.node import Neo4jNode
from neo4j_ogm.fields import WithOptions
from neo4j_ogm.queries.query_builder import QueryBuilder


class MetaModel(BaseModel):
    msg: str = "METADATA"


class TestModel(Neo4jNode):
    __labels__ = ["Test", "Node"]

    id: str
    name: str
    age: int
    friends: list[str] = []
    meta: MetaModel = MetaModel()
    json_data: Dict[str, str] = {"key": "value"}


async def main():
    client = Neo4jClient()
    client.connect(uri="bolt://localhost:7687", auth=("neo4j", "password"))
    await client.drop_constraints()
    await client.drop_indexes()
    await client.drop_nodes()
    await client.register_models(models=[TestModel])

    # for i in range(20):
    # instance = await TestModel(id=str(uuid4()), name=f"instance-{i}", age=random.randint(1, 100)).create()

    # result = await TestModel.find_many({"age": {"$or": [{"$and": [{"$gt": 30}, {"$lte": 45}]}, {"$eq": 60}]}})

    instance = await TestModel(id=str(uuid4()), name=f"instance-0", age=random.randint(1, 100)).create()
    instance.name = "instance-updated"
    instance.age = 20
    await instance.update()
    await instance.delete()

    print("DONE")


asyncio.run(main())
