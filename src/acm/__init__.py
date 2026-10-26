"""Actions Consequential Model (ACM).

Built on the Meaning Language Model: MLM turns an action phrase into Universal
Phrase DNA (who does what, to whom, where, when, why); ACM turns that frame into a
graph of the full action in its context and predicts what the action changes,
circle by circle:

* the **actor** (WHO) - the model itself when the actor is "I",
* the **subjects impacted** (WHAT / TO WHOM),
* **other actors** - their goals and their actions,
* then outwards, layer by layer: the **local environment** acted upon (WHERE),
  its **neighbours**, the **connected** businesses, enterprises and systems, its
  **city**, its **country**, **society** and the **earth**.

The output is a structured report, a Mermaid mind map, and a vector graph that can
be stored and searched.
"""

from acm.engine import ConsequenceEngine
from acm.schema import ConsequenceReport, RelationStatus, Target

__all__ = ["ConsequenceEngine", "ConsequenceReport", "RelationStatus", "Target"]
