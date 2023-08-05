# Neo4j Object Graph Mapper
A asynchronous wrapper library around **Neo4j's python driver** which provides a **structured and easy** approach to working with
Neo4j databases and cypher queries. This library makes heavy use of `pydantic` and it's validation capabilities.



## ⚡️ Quick start <a name="quick-start"></a>

Before we can interact with the database, we have to do 3 simple things:

1. Connect our client to our database
2. Define our data structures with `NodeModels and RelationshipModels`
3. Register our models with the client (Can be skipped, which brings some drawbacks, more talked about in
  [`Database client`](#database-client))


#### Connecting the client
Before you can interact with the database in any way, you have to open a connection. This can be achieved by initializing
the `Neo4jClient` class and calling the `Neo4jClient.connect()` method.

```python
from neo4j_ogm import Neo4jClient

my_client = Neo4jClient()
my_client.connect(uri="uri-to-your-database", auth=("your-username", "your-password"))

# It is also possible to chain the connect method when creating the client instance
my_client = Neo4jClient().connect(uri="uri-to-your-database", auth=("your-username", "your-password"))
```


#### Modeling out data
After we have established a connection to our database, we can start to model our data. Neo4j stores data in the form of
`nodes and relationships`. With neo4j-ogm, you mimic this approach by defining you nodes, relationships and the connections
between them as `database models`. The attributes of the models reflect the properties of the nodes and relationships in
the database. Additionally, you can define `Settings` for your models, more about that in the [`Defining node settings`](#node-settings)
and [`Defining relationship settings`](#relationship-settings) sections.

```python
from neo4j_ogm import NodeModel, RelationshipModel, RelationshipDirection, RelationshipProperty
from datetime import datetime
from uuid import UUID


# A class representing a relationship in the database
class Implemented(RelationshipModel):
  id: UUID
  killed_production: bool

  class Settings:
    type = "IMPLEMENTED_BUT_IN"


# Classes representing nodes in the database
class Bug(NodeModel):
  created_at: datetime

  class Settings:
    labels = "Bug"


class Developer(NodeModel):
  name: str
  age: int

  caused_bugs = RelationshipProperty(
    target_model=Bug,
    relationship_model=Implemented,
    direction=RelationshipPropertyDirection.OUTGOING
    allow_multiple=True
  )

  class Settings:
    labels = {"Person", "Developer"}
```


#### Interacting with the database
Now all we have to do is register the models we defined with our client and we are ready to go. After registering the models,
the client will automatically create the necessary constraints and indexes for the models, if any are defined
(more about that in the [`Indexes and constraints`](#indexes-and-constraints) section). We can now start to query our database,
create new nodes or relationships and much more.

```python
# Registering the models with the client
async def main() -> None:
  await my_client.register_models([Developer, Bug, Implemented])

  # Create a new `Developer` instance and save it to the database
  developer = await Developer(name="John", age=21).create()

  # More fun stuff down here
  ...
```
<br />



## 📚 Documentation
The following documentation will cover all the features of neo4j-ogm and how to use them in greater detail. If you are
looking for a quick start, please refer to the [`Quick start`](#quick-start) section.


### Node models <a name="node-models"></a>
Node models are used to represent nodes in the database. They are defined by inheriting from the `NodeModel` class and
defining the properties of the node as class attributes.


#### Defining node properties <a name="node-properties"></a>
If you want to define a property for a node, you have to define it as a class attribute. The name of the attribute will
be used as the name of the property in the database. The type of the attribute will be used to validate the property
value. If the validation fails, a `ValidationError` will be raised. The following example shows how to define a node.
If this sounds familiar to you, it is because this library makes heavy use of `pydantic's BaseModel` and validation
under the hood. If you want to learn more about pydantic, please refer to the [pydantic documentation](https://docs.pydantic.dev/1.10/).

> ❗️ **Note:** Since Neo4j does not support nested properties, all dictionaries and nested models will be flattened when defining them
> as properties. This means that all dictionaries and nested models will be converted to a string and stored as a string property.
> This also means that you can not define indexes or constraints on nested properties. When inflating the model, the string will be
> converted back to a dictionary or model.

```python
from neo4j_ogm import NodeModel
from pydantic import Field, validator
from uuid import uuid4, UUID


# This class represents a node in the database with the label "Developer"
class Developer(NodeModel):
  id: UUID = Field(default_factory=uuid4)  # All data types supported by pydantic are supported by neo4j-ogm
  name: str
  age: int = Field(gt=0)  # You can use pydantic's Field class to define additional validation rules
  likes_his_job: bool

  # You can also define custom validators for your properties
  @validator("likes_his_job")
  def validate_likes_his_job(cls, v: bool) -> bool:
    if v is False:
      raise ValueError("Welcome to the club!")
    return v
```

Should you, for whatever reason, name your class with something other than PascalCase and not define any labels for the class, the automatically generated label will be the `PascalCase` version of the class name. For example, if you have a class named `my_class`, the automatically generated label will be `MyClass`.

> You can define whatever properties you want, but you can not use the following property names, as they are reserved for
> internal use and to prevent conflicts when exporting models:
> - `element_id`
> - `modified_properties`


#### Defining node settings <a name="node-settings"></a>
Node settings are used to define additional settings for a node model. They are defined by creating a class named
`Settings` inside the node model class and defining the settings as class attributes. The following example shows how
to define node settings.

```python
from neo4j_ogm import NodeModel

class Developer(NodeModel):
  # Properties would go here

  class Settings:
    exclude_from_export = {"id"}
    pre_hooks = {"create": ["set_default_values"]}
    labels = {"Person", "Developer"}
```
<br />

**Available node settings**:

| Setting name        | Type                                           | Description                                                                                                                                                                                                                                       |
| ------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| exclude_from_export | **Set[str]**                                   | A set of property names that should be excluded model exports (see [`Importing and exporting models`](#importing-and-exporting-models))                                                                                                           |
| pre_hooks           | **Dict[str, Union[List[Callable], Callable]]** | A dictionary of pre hooks that should be executed before a certain action (see [`Pre hooks`](#pre-hooks))                                                                                                                                         |
| post_hooks          | **Dict[str, Union[List[Callable], Callable]]** | A dictionary of post hooks that should be executed after a certain action (see [`Post hooks`](#post-hooks))                                                                                                                                       |
| labels              | **Union[str, Set[str]]**                       | The labels that should be used for the node in the database. If a string is provided, it will be converted to a set with one element. If no labels are defined, the class name will be used as the label, converted to `PascalCase` if necessary. |


#### Working with model methods <a name="working-with-node-models-methods"></a>
Node models offer a variety of methods to interact with the database. In this section we will cover all of them.
> All of the following examples will use the `Developer` model defined in the [`Defining node properties`](#defining-node-properties)


#### **`NodeInstance.create()`**
Creates a new node in the database with the values of the model instance. Here is an example
of how to use it:

```python
async def main() -> None:
  developer = Developer(
    name="John",
    age=24,
    likes_his_job=True
  )

  print(developer)  # Not yet hydrated

  await developer.create()  # New node with the defined properties on `developer` is created
  print(developer)  # You can keep using the instance like normal
```
<br />

After creating the node in the database, the instance will be marked as `alive` (This can be seen by running the above code). This means you
can now call other methods on the instance like `.delete()` or `.update()`. If you were to try the same on a instance which has not been saved to
the database, neo4j-ogm kindly reminds you of your mistake with a `InstanceNotHydrated` exception.


#### **`NodeInstance.update()`**
Updates an existing node in the database which corresponds to your local instance. The updated values defined in the instance will overwrite any
properties in the database. All model instances provide a `modified_properties` attribute which contains a set of all properties that have been
modified since the instance was last hydrated. This set is used to determine which properties should be updated in the database.

This attribute can come in handy when you want to do certain actions when a particular property is updated. For example, you could use it to
automatically update a `last_modified` property on your node. A conrete example of this can be found in the [Hooks](#hooks) section.

```python
async def main() -> None:
  developer = await Developer(
    name="John",
    age=24,
    likes_his_job=True
  ).create()

  # Update instance with new values
  developer.age = 27
  await developer.update()  # Updates node in database and syncs local instance
```


#### **`NodeInstance.delete()`**
Deletes the node linked to your local instance.

```python
async def main() -> None:
  developer = await Developer(
    name="John",
    age=24,
    likes_his_job=True
  ).create()

  await developer.delete()  # Deletes node in database
```
<br />

After deleting the node in the database, the instance will be marked as `destroyed`. This means you can no longer call any methods on the instance
except for `.create()`, which will create a new node with the same properties as the instance. Still, if you were to try and call any other method
on the instance, you will get a `InstanceDestroyed` exception.


#### **`NodeInstance.refresh()`**
Updates the local instance with the values from the database. This is useful if you want to make sure that the instance is up to date with the
database.

```python
async def main() -> None:
  developer = await Developer(
    name="John",
    age=24,
    likes_his_job=True
  ).create()

  # Something on the local instance changes (Maybe for no apparent reason)
  developer.age = 27
  await developer.refresh()

  print(developer.age)  # 24
```


#### **`NodeInstance.find_connected_nodes()`**
Returns all nodes connected to the instance over multiple hops. This method gives you the ability to use the same filters as you would with
other methods, but with the added benefit of being able to filter on the relationships between the nodes. The method takes two arguments:

- `filters`: A dictionary of filters that should be applied to the query. This filter is a special multi-hop filter (see [`Filters on relationships with multiple hops`](#filters-on-relationships-with-multiple-hops))
- `options`: Options which determine how the nodes should be returned. For more information on options, see [`Filter options`](#filter-options).

```python
async def main() -> None:
  developer = await Developer(
    name="John",
    age=24,
    likes_his_job=True
  ).create()

  # Find all company nodes that the developer works at where all relationships of type `PAYMENT` have
  # the property `pays_well` set to `True`
  developer.find_connected_nodes({
    "$minHops": 2,
    "$maxHops": 7,
    "$relationships": [
      {
        "$type": "PAYMENT",
        "pays_well": True
      }
    ],
    "$node": {
      "$labels": ["Company"],
    }
  })
```
<br />

The above example will return all company nodes that the developer works at where all relationships of type `PAYMENT` have the property `pays_well`
set to `True`. The returned value will be a list of instances of the model `Company`. For more complex examples, multiple filters for multiple relationships
can be defined.


#### **`NodeModel.find_one()`**
Finds and returns a single node from the database. If no node is found, `None` is returned. The method takes one argument:

- `filters`: Filters which determine which nodes should be returned. For more information on filters, see [`Filters and options`](#filters-and-options).

The following example shows how to use it:

```python
async def main() -> None:
  developer = await Developer.find_one({"name": "John"})  # Return the first encountered node where the name property equals `John`

  if developer is None:
    # No developer with the name "John" was found
    ...
```


#### **`NodeModel.find_many()`**
A similar method to `NodeModel.find_one()`, but instead of returning a single node, it returns a list of nodes. If no nodes are found, an empty list is returned. The method takes two arguments:

- `filters`: Filters which determine which nodes should be returned. For more information on filters, see [`Filters and options`](#filters-and-options). Can be
  omitted to return all nodes.
- `options`: Options which determine how the nodes should be returned. For more information on options, see [`Filter options`](#filter-options).

```python
async def main() -> None:
  # Return the first 20 encountered nodes where the name property equals `John`
  developers = await Developer.find_many({"name": "John"}, {"limit": 20})
```


#### **`NodeModel.update_one()`**
Updates a single node in the database. The method takes three arguments:

- `update`: The properties which should be updated on the node. Properties which are not defined in the model will be ignored.
- `filters`: Filters which determine which node should be updated. For more information on filters, see [`Filters and options`](#filters-and-options).
- `new`: Whether or not the updated node should be returned. Defaults to `False`.

```python
async def main() -> None:
  # Update the first encountered node where the name property equals `John`
  developer = await Developer.update_one({"name": "Johnny"}, {"name": "John"}, new=True)

  print(developer.name)  # Prints `Johnny` since new=True was defined
```


#### **`NodeModel.update_many()`**
Updates multiple nodes in the database. The method takes three arguments:

- `update`: The properties which should be updated on the nodes. Properties which are not defined in the model will be ignored.
- `filters`: Filters which determine which nodes should be updated. For more information on filters, see [`Filters and options`](#filters-and-options).
- `new`: Whether or not the updated nodes should be returned. Defaults to `False`.

```python
async def main() -> None:
  # Update all encountered nodes where the name property equals `John`
  developers = await Developer.update_many({"name": "Johnny"}, {"name": "John"})

  print(type(developers)) # Prints `list`
  print(developers[0].name)  # Prints `John` since new was not defined and defaults to false
```


#### **`NodeModel.delete_one()`**
Deletes a single node in the database. The method takes one argument:

- `filters`: Filters which determine which nodes should be deleted. For more information on filters, see [`Filters and options`](#filters-and-options).

Unlike the other methods, this method does not return a instance of the model. Instead, it returns the amount of nodes which were deleted.

```python
async def main() -> None:
  # Delete the first encountered node where the name property equals `John`
  developer_count = await Developer.delete_one({"name": "John"})

  print(developer_count) # 1
```


#### **`NodeModel.delete_many()`**
Deletes multiple nodes in the database. The method one argument:

- `filters`: Filters which determine which nodes should be deleted. For more information on filters, see [`Filters and options`](#filters-and-options).

THis method, like `NodeModel.delete_one()`, returns the amount of nodes which were deleted.

```python
async def main() -> None:
  # Delete all encountered nodes where the name property equals `John`
  developer_count = await Developer.delete_many({"name": "John"})

  print(developer_count) # However many nodes were deleted
```


#### **`NodeModel.count()`**
Returns the count of nodes matched by the filters. The method takes one argument:

- `filters`: Filters which determine which nodes are matched. For more information on filters, see [`Filters and options`](#filters-and-options).


```python
async def main() -> None:
  # Counts all encountered nodes where the name property equals `John`
  developer_count = await Developer.count({"name": "John"})

  print(developer_count) # However many nodes were deleted
```


### Relationship models <a name="relationship-models"></a>
Relationships define connections between nodes. They are defined in the same way as node models, but with a few differences. They are defined using the `RelationshipModel` class.


#### Defining relationship properties <a name="relationship-properties-on-node-models"></a>
Properties on relationships are defined in the same way as properties on node models. Since it, just like node models, is a subclass of `pydantic.BaseModel`, the same rules apply. The following example shows how to define a relationship model:

```python
from neo4j_ogm import RelationshipModel
from pydantic import Field, validator
from uuid import uuid4, UUID


# This class represents a relationship in the database of type "IMPLEMENTED"
# It has two properties, "id" and "killed_production"
class Implemented(RelationshipModel):
  id: UUID = Field(default_factory=uuid4)  # Same rules apply as with node models
  killed_production: bool = Field(default=False)
```

You may have noticed that the type is not exactly the same as the class name. This is because neo4j-ogm converts the class name to a string which matches the recommended naming convention for relationships in Neo4j. The class name is converted to `SCREAMING_SNAKE_CASE`. For example, the class `MyCoolRelationship` is converted to `MY_COOL_RELATIONSHIP`.

> ❗️ **Note:** The same constraints apply to relationship properties as to node properties. For more information, see [`Defining node properties`](#defining-node-properties).


#### Defining relationship settings <a name="relationship-settings"></a>
Relationships can be defined with a few settings. These settings are, like with node models, defined in a nested `Settings` class in the model.

```python
from neo4j_ogm import RelationshipModel

class Implemented(RelationshipModel):
  # Properties would go here

  class Settings:
    post_hooks = {"create": ["alert_developer"]}
    type = "IMPLEMENTED_BUT_IN"
```
<br />

**Available relationship settings**:

| Setting name        | Type                                           | Description                                                                                                                                                                    |
| ------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| exclude_from_export | **Set[str]**                                   | A set of property names that should be excluded model exports (see [`Importing and exporting models`](#importing-and-exporting-models))                                        |
| pre_hooks           | **Dict[str, Union[List[Callable], Callable]]** | A dictionary of pre hooks that should be executed before a certain action (see [`Pre hooks`](#pre-hooks))                                                                      |
| post_hooks          | **Dict[str, Union[List[Callable], Callable]]** | A dictionary of post hooks that should be executed after a certain action (see [`Post hooks`](#post-hooks))                                                                    |
| type                | **str**                                        | The type of the relationship. Defaults to the name of the class converted to `SCREAMING_SNAKE_CASE`. For example, `MyCoolRelationship` is converted to `MY_COOL_RELATIONSHIP`. |


#### Working with model methods <a name="working-with-relationship-models-methods"></a>
Relationship models have, for the most part, the same methods as node models. Apart from the `NodeInstance.find_connected_nodes()` and `NodeInstance.create()` methods, every method is also available on relationship models, which a few additional ones. We will not go over the methods both node and relationship models have in common, but instead focus on the ones that are unique to relationship models.

Additionally, relationship models do not implement all filters that node models do. This is more talked about in [`Basic filters`](#basic-filters).


#### **`RelationshipInstance.start_node()`**
Gets the start node of the current relationship. This method takes no arguments and returns an instance of the node model. For example, if we have a relationship between a `Developer` and a `Project` with the direction `OUTGOING`, the `start_node()` method will return an instance of the `Developer` model.

```python
async def main() -> None:
  # `implemented` represents a relationship between a `Developer` and a `Project`
  # with the direction `OUTGOING`
  developer = await implemented.start_node()

  print(developer) # An hydrated instance of the `Developer` model
```


#### **`RelationshipInstance.end_node()`**
Gets the end node of the current relationship. This method takes no arguments and returns an instance of the node model. For example, if we have a relationship between a `Developer` and a `Project` with the direction `OUTGOING`, the `end_node()` method will return an instance of the `Project` model.

```python
async def main() -> None:
  # `implemented` represents a relationship between a `Developer` and a `Project`
  # with the direction `OUTGOING`
  project = await implemented.start_node()

  print(project) # An hydrated instance of the `Project` model
```


### Relationship properties on node models <a name="relationship-properties-on-node-models"></a>
neo4j-ogm allows you to define direct relationships (single-hop connections) between different nodes directly on the node models themselves. This is done by defining a property on the node model with the type `RelationshipProperty`. The following example shows how to define a relationship property:


#### Defining connections between node models <a name="defining-connections-between-node-models"></a>
Let's say we have 3 models: `Developer`, `Project` and `Implemented`. The `Developer` model represents a developer, the `Project` model represents a project and the `Implemented` model represents a relationship between a developer and a project.

Rather than querying the connection between a developer and a project with the `NodeModel.find_connected_nodes()` method, we can define a direct connection between the two models. This is done by defining a property on the `Developer` model with the type `RelationshipProperty`. The following example shows how to define a relationship property:

```python
from neo4j_ogm import NodeModel, RelationshipModel, RelationshipProperty, RelationshipPropertyDirection
from pydantic import Field
from uuid import uuid4, UUID


class Implemented(RelationshipModel):
  id: UUID = Field(default_factory=uuid4)
  killed_production: bool = Field(default=False)


class Developer(NodeModel):
  id: UUID = Field(default_factory=uuid4)
  name: str

  # Here we define a direct relationship between the `Developer` and `Project` models
  projects: RelationshipProperty["Project", "Implemented"] = RelationshipProperty(
    target_model="Project",
    relationship_model=Implemented,
    direction=RelationshipPropertyDirection.OUTGOING,
    allow_multiple=True
  )


class Project(NodeModel):
  id: UUID = Field(default_factory=uuid4)
  finished: bool
```

> ❗️ **Note:** If you want to use the defined connection between models from both node models, it has to be defined on both.

In the example above example, we define a direct connection between the `Developer` and the `Project` models. We specify a few things for the relationship between the two:

- `target_model`: The target model (other end of the relationship) is the `Project` model. This can either be the class itself or a string with the **class name**.
- `relationship_model`: The relationship between the two is defined by the `Implemented` class. This can, again, be defined as a string representing the class or the class itself.
- `direction`: The direction of the relationship should be `OUTGOING`, meaning that the **Developer node is the start node** and the **Project node is the end node**
- `allow_multiple`: We allow multiple relationships of the same type between the same nodes. By default, neo4j-ogm only allows one relationship of each type between two nodes. But there are certain use-cases where is is not wanted. In out example, one developer could implement multiple bugs in a project.

> ❗️ **Note:** If you provide the target or relationship model as a string, you **have** to define the type for the relationship property by passing the types for the models. This has to be done because python can't infer the type of the returned relationships or models if they are defined as a string. You can define the types using the generic parameters of the `RelationshipProperty` class:
>
> ```python
> property_name: RelationshipProperty[YourNodeModel, YourRelationshipModel] = RelationshipProperty(...)
> ```


#### Relationship property settings <a name="relationship-property-settings"></a>
#### Working with connections between node models <a name="working-with-connections-between-node-models"></a>


### Filters and options <a name="filters-and-options"></a>
#### Basic filters <a name="available-filters"></a>
#### Pattern matching <a name="pattern-matching"></a>
#### Filters on relationships with multiple hops <a name="filters-on-relationships-with-multiple-hops"></a>
#### Filter options <a name="filter-options"></a>


### Hooks <a name="hooks"></a>
#### Pre hooks <a name="pre-hooks"></a>
#### Post hooks <a name="post-hooks"></a>
#### Global vs local hooks <a name="global-vs-local-hooks"></a>


### Importing and exporting models <a name="importing-and-exporting-models"></a>
#### Importing models <a name="importing-models"></a>
#### Exporting models <a name="exporting-models"></a>


### Indexes and constraints <a name="indexes-and-constraints"></a>
#### Indexes <a name="indexes"></a>
#### Constraints <a name="constraints"></a>


### Database client <a name="database-client"></a>
#### Connecting to the database <a name="connecting-to-the-database"></a>
#### Closing the connection <a name="closing-the-connection"></a>
#### Registering models <a name="registering-models"></a>
#### Running cypher queries <a name="running-cypher-queries"></a>
#### Batched queries together <a name="batched-queries-together"></a>
#### Manually creating indexes and constraints <a name="manually-creating-indexes-and-constraints"></a>
#### Drop all indexes, constraints and nodes <a name="drop-all-indexes-constraints-and-nodes"></a>
