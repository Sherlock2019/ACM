"""Consequence Action Model (CAM).

Built on the Meaning Language Model: MLM turns an action phrase into Universal
Phrase DNA (who does what, to whom, where, when, why); CAM turns that frame into a
graph of the full action in its context and predicts what the action changes,
circle by circle:

* the **actor** (WHO) - the model itself when the actor is "I",
* the **subjects impacted** (WHAT / TO WHOM),
* **other actors** - their goals and their actions,
* the **environment** acted upon (WHERE),
* **society** and the **earth**.

The output is a structured report, a Mermaid mind map, and a vector graph that can
be stored and searched.
"""

from cam.engine import ConsequenceEngine
from cam.schema import ConsequenceReport, RelationStatus, Target

__all__ = ["ConsequenceEngine", "ConsequenceReport", "RelationStatus", "Target"]
