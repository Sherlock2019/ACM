"""Action Reaction Model (ARM).

Built on the Meaning Language Model: MLM turns an action phrase into Universal
Phrase DNA (who does what, to whom, where, when, why); ARM turns that frame into a
graph of the full action in its context and predicts what the action changes,
circle by circle:

* the **actor** (WHO) - the model itself when the actor is "I",
* the **subjects impacted** (WHAT / TO WHOM),
* **other actors** - their goals and their actions,
* then its **blast radius**, layer by layer: the **local environment** acted upon
  (WHERE), its **neighbours**, the **organization** it belongs to (business,
  enterprise, institution, system), its **city**, its **country**, **society**
  and the **earth**.

The output is a structured report, a Mermaid mind map, and a vector graph that can
be stored and searched.
"""

from acm.engine import ConsequenceEngine
from acm.schema import ConsequenceReport, RelationStatus, Target

__all__ = ["ConsequenceEngine", "ConsequenceReport", "RelationStatus", "Target"]
