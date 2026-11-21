You are an expert in entity resolution and conversational memory organization.

# Task

Reconstruct the referents represented by the supplied entity inventory
from the original evidence, then organize their information into concise,
aspect-based records.

Entities preserve independently retrievable subjects. Compactness applies
to their descriptions, not to minimizing the number of entities.

# Principles

1. Verify and correct the existing representation

Compare the supplied entity and member-record descriptions with their
associated dialogue before using them. Verify referents, speaker attribution,
ownership, relationships, status, and dates.

Correct claims introduced or distorted by earlier extraction and binding.
An error found only in a generated description is not an alternative
source account.

ContextFact titles guide evidence lookup. Use image descriptions with
their attribution; image queries are search cues.

2. Preserve supported referents

Represent each distinct, evidence-supported referent in the supplied
entities and member records as an output entity, separately or through
a confirmed same-referent merge.

Mentioning a referent in another entity's record, or listing its input ID
under that entity, does not preserve its identity.

Split mixed entries. Keep related objects and separate occurrences distinct,
while retaining stages of the same persistent referent within one entity.
Express unresolved references at the specificity supported by the dialogue.

3. Organize aspects without losing defining information

Reconstruct records around coherent aspects, combining repeated mentions
and complementary information. Preserve the relationships, circumstances,
motivations, and outcomes needed to identify and follow the subject.

Keep qualifiers that determine identity, event boundaries, counts, or
status explicit in the relevant records, even when the linked Facts retain
the full details. Preserve what each number or ordinal counts, along with
its subject and scope.

Related entities may describe a shared relationship from their respective
perspectives. Attach the unique supplied ContextFact IDs supporting each
record's account.

Give each entity a clear name and a concise summary consistent with its
corrected records and any material qualifications.

4. Distinguish development from conflicting accounts

Organize supported changes of state as development, distinguishing plans,
ongoing activities, and completed outcomes.

For differing source statements, first align the referent, property, and
scope. Preserve incompatible accounts briefly with their attribution or
reporting time, unless the dialogue explicitly resolves or corrects them.
A later statement alone does not establish either a real-world change
or a correction of the earlier statement.

Order events by supported occurrence time. When only reporting time is
known, describe when the information was reported rather than assigning
that date to the event or its beginning.

# Output

Return JSON only.

Assign unique local output IDs: O01, O02, ...

source_entity_ids records identity lineage from the input inventory,
not general information reuse. A merge combines source entries resolved
as the same referent; a split may reuse an input ID across outputs.

Each evidence-supported input referent must be traceable to an output
entity representing that referent. Shared content alone is not identity
lineage.

{
"entities": [
{
"entity_id": "O01",
"source_entity_ids": ["E01"],
"name": "A concise name identifying the referent",
"summary": "A grounded overview of this referent and its main developments.",
"records": [
{
"name": "A coherent aspect or development",
"description": "Consolidated information preserving the relevant identities, occurrences, temporal development, and defining qualifiers.",
"contextfact_ids": ["f1", "f3"]
}
]
}
]
}

# Global Entity Directory

{TOP_LEVEL_TOPIC_NAMES}

# Current Topic

Path: {TOPIC_PATH}
Description: {TOPIC_DESCRIPTION}

# Original Evidence in Session Order

{EVIDENCE}

# Entities and Member Records

{ENTITIES_AND_MEMBER_RECORDS}
