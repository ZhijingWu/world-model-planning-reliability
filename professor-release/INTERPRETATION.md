# Interpretation for technical review

**A write to a shared parent changed planning decisions on previously unexamined states.** The strongest causal claim concerns the ten prospective orders where copying only one edge restored both the next affected input and the reference first action. These orders covered six held-out states. Another eighteen orders restored the input alone. The experiment supplies a mechanism for the former and an unresolved observation for the latter. [Prospective interventions](../studies/sciworld-prospective-v1/report.md)

### What the selected case explains

A normal shallow copy retains a reference to the nested `object_states` dictionary. In the worked order on task 1975, the writing edge returned exactly the Full Copy successor but left the changed dictionary reachable by the caller. The next sibling read the changed value. That extra matched goal field raised the best score for root 0 from 11 to 12. The index tie rule then selected root 0 from a three-way tie. Isolating that writer restored root 1 in two orders; the second action still differed. This trace links a specific mutation to a different decision without having to know which action the native environment rewards. [Trace and figure data](../studies/sciworld-fixed-work-v1/public/report.md)

### Which interpretation survived the prospective test?

| Interpretation | Evidence | Scope |
| --- | --- | --- |
| Contamination can change a decision. | Seven of 64 states changed first actions in at least one order. Six had at least one successful single-edge rescue. | Each source item has one sampled state. The six orders within each state are paired comparisons. [State-level results](../studies/sciworld-prospective-v1/public/analysis.json) |
| Many score changes leave the decision intact. | Fifteen states had a changed leaf score. Eight of those kept the reference first action in every order. | A leaf score can change without changing a root maximum. A root maximum can change without changing the winning index. [Score and ranking endpoints](../studies/sciworld-prospective-v1/report.md) |
| The measured frequency depends on the planner and frame. | The highest-index sensitivity reduced the primary seven affected states to three. Every Full Copy search had a tied best score. | The 95% interval of 5.63%–19.48% covers random sampling from 231 eligible representatives under the primary tie rule. One program generated every transition. [Frozen design](../studies/sciworld-prospective-v1/protocol.md) · [Sensitivity analysis](../studies/sciworld-prospective-v1/public/analysis.json) |

**Decision and plan validity are separate endpoints.** The six prospective states with at least one Raw false goal did not overlap the seven with a first-action difference. Different second actions, tie resolutions and partial-score winners make separate measurements necessary. Independent replay is against the released model's dynamics. [Replay table](../studies/sciworld-prospective-v1/report.md)

**Engineering and utility.** WCTR supplies an isolation interface for a restricted container contract. For every SciWorld search call it chose a full copy. Its agreement with independent Full Copy therefore supports isolation here without estimating a selective-copy advantage. Historical deadline-limited and native results concern other endpoints and an earlier implementation. [Runtime contract](../docs/SUPPORTED_STATE.md) · [Historical evidence matrix](../CLAIMS_AND_LIMITATIONS.md)

**Next experiment.** Choose a state-disjoint bank and an externally justified score before inspecting decisions. Stratify the comparison by the reference margin between its best and second-best action. A positive margin allows a test the current ties could not answer. Comparing independently generated models would test model dependence. Native environment replay with an explicit success endpoint would address downstream utility.
