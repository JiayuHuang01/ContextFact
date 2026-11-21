# Task
Convert one raw conversation session into a chronological list of context-preserving facts and a linked entity index in one output.

# Input
```text
CONVERSATION DATE: <date, including the weekday>

EVIDENCE:
D<session>:<turn> <Speaker>: <text> [IMG blip="<caption>" query="<query>"]
...
```
The `IMG` part is optional and belongs to the same source turn.

# Principles

1. **Identify and regroup core facts**
   - Read the whole session before forming any ContextFacts. First identify the core facts in the conversation; do not create one fact from each turn. A core fact is a specific event, action, state, plan, experience, preference, attribute, personal detail, belief, realization, decision, outcome, or change—not a broad topic or everything said about one participant.
   - For each new clause, decide whether it:
     (a) further develops an existing core fact by identifying, describing, explaining, clarifying, or evaluating that same fact; providing its circumstances, reasons, progress, outcome, or event-specific feelings; or directly reacting to it through encouragement, gratitude, agreement, or another immediate response; or
     (b) introduces another independently meaningful memory focus, such as a distinct occurrence, plan, state, habitual practice, preference, general belief, realization, decision, or lasting change that is not limited to describing or reacting to the current fact.
     Attach (a) to the ContextFact it supports. Create or resume a separate ContextFact for (b). Classifying a clause as supporting context does not permit omitting it or replacing its specific meaning with a broader summary.
   - After identifying the focuses, regroup non-adjacent clauses that belong to the same concrete fact. If one utterance reacts to one core fact and introduces or resumes another, divide it by meaning. One source turn may support multiple ContextFacts, and one ContextFact may use non-consecutive turns.

2. **Self-contained references and attribution**
   - Make each ContextFact understandable on its own by explicitly identifying the relevant people, objects, events, and activities when needed.
   - Resolve omitted subjects, pronouns, and vague references such as "this" or "that one" when their referents are clear. Pronouns may remain when the referent is explicit and unambiguous within the same ContextFact. If a reference cannot be resolved from the evidence, preserve the original wording rather than guessing.
   - Preserve participant roles and perspective. Every action, experience, feeling, belief, evaluation, and reaction must remain attributed to its original speaker or subject.

3. **Preserve the original expression**
   - Keep the original wording, tone, specific descriptions, intensifiers, negation, modality, and uncertainty as much as possible. Make only the grammatical changes needed for attribution, pronoun resolution, and readability. Never turn a plan into a completed action, a possibility into certainty, or one participant's statement into the other's experience.
   - Preserve specific actions, identifying details, quoted wording, and the scope of personal statements; do not replace them with broader activities, interpretations, or summaries.

4. **Remove non-memory-bearing content**
   - Omit greetings, farewells, filler, content-free acknowledgements, exact repetition, and routine closing remarks that add no substantive information. Preserve substantive personal and relationship information wherever it appears.
   - Interpret each answer together with the question it addresses. Preserve the target, requested attribute or relationship, and any comparison, contrast, negation, or time scope needed to retain the answer's meaning as a self-contained fact.
   - Omit purely information-seeking questions and the narration that they were asked, while retaining their answers and substantive factual content. State only what the exchange supports: an unconfirmed question premise or proposed alternative must not become an established fact.

5. **Image rule**
   `blip` provides a visual description of the shared photo; `query` is only the phrase used to search for it and may not match the photo.
   - Use a photo when it identifies or clarifies the concrete subject presented in its source turn, or when the surrounding conversation discusses it. Sharing a broad topic with the text is not sufficient. Omit generic, decorative, unrelated, or conflicting image information.
   - For a relevant photo, retain concrete visual features and any depicted wording explicitly provided in blip when they distinguish the subject or contribute to understanding the discussion. Integrate relevant visual information into the ContextFact for the pictured subject, using wording such as "shared a photo of ...". A photo alone does not require a separate ContextFact.
   - Use the conversation to establish personal attribution and factual connections. A visible feature or inscription does not by itself establish who owns or created the subject, or which real-world event it depicts. Use a query-only detail only when independently supported by the conversation and not contradicted by blip.

6. **Preserve dual-format time references**
   - Preserve time expressions in the format: relative time (absolute date or range), retaining the original precision.
   - If a time expression is clearly resolvable from the source context and session date but lacks an absolute value, append it. If an existing absolute value is clearly incorrect, correct it.

7. **Extract and link entities**
   - Extract specific, context-grounded entities from the raw session as
     retrieval entry points, including referents embedded in descriptions.
     Link each entity to all ContextFacts that provide substantive
     information about it.
   - Include people (excluding the speakers themselves), animals, places,
     organizations, works, objects, foods, recipes, projects, and events.
   - Do not extract either speaker as an entity. A speaker-related entry must
     identify a specific object, event, activity, or project associated with
     that speaker, not the person as a whole.
   - Use stated names or concise identifying labels, adding ownership or
     distinguishing context when needed. Keep each entry centered on one
     referent rather than a generic keyword, broad theme, or separate aspect
     of the same entity.

# Output

Return valid JSON only, using this structure:

```json
{
  "contextfacts": [
    {
      "contextfact_id": "Unique local ID: CF1, CF2, ...; ordered by the first appearance of each core fact.",
      "title": "A short label identifying the main person and core event, state, or object.",
      "content": "The self-contained ContextFact.",
      "turn_ids": ["Original turn IDs supporting the content, deduplicated and in conversation order."]
    }
  ],
  "entities": [
    {
      "name": "The stated name or a concise identifying label; exclude the two speaker names.",
      "description": "One short, raw-session-grounded sentence identifying the entity and its participant association or distinguishing context",
      "contextfact_ids": ["All generated ContextFact IDs providing substantive information about the entity; use [] if none."]
    }
  ]
}
```

# Example 1: Interleaved facts and cross-fact entity links

## Input

SPEAKERS: Dave, Calvin
CONVERSATION DATE: Sunday, May 15, 2022

D1:1 Dave: I completed my first charity run last Sunday (May 8, 2022). I was exhausted
near the end, but really proud that I finished.
D1:2 Calvin: Finishing despite exhaustion shows real determination.
I'm proud of you!
D1:3 Dave: Your encouragement means a lot. Our team also raised $1,200
for the children's library.
D1:4 Calvin: That makes the run even more meaningful. The children will
really benefit. By the way, I enrolled in an evening graphic-design course
on Tuesday (May 10, 2022) because I want to design websites for nonprofits.
D1:5 Dave: That course suits your creativity! I trained before work for
two months for the run. Here's a finish-line photo. The library emailed us
today (May 15, 2022) and said the donation will let it buy about 80 books.
[IMG blip="a group of runners smiling beneath a finish-line banner"
query="charity run finish line"]
D1:6 Calvin: Everyone looks happy in the photo—a great reminder of what
your team achieved. My course lasts eight weeks, and its final project is
a website for a local food pantry. I'm nervous about balancing it with
my weekend shifts.
D1:7 Dave: The food-pantry website sounds meaningful. I hope you'll show
it to me when it's finished.
D1:8 Calvin: Your support makes me feel more confident. Anyway, I need
to make dinner. Bye!

## Output

```json
{
  "contextfacts": [
    {
      "contextfact_id": "CF1",
      "title": "Dave's first charity run",
      "content": "Dave completed his first charity run last Sunday (May 8, 2022). He trained before work for two months and was exhausted near the end, but really proud he finished. Dave shared a photo of runners smiling beneath a finish-line banner. Calvin thought Dave showed real determination, was proud of him, and called the photo a great reminder of the team's achievement. Dave said Calvin's encouragement meant a lot.",
      "turn_ids": ["D1:1", "D1:2", "D1:3", "D1:5", "D1:6"]
    },
    {
      "contextfact_id": "CF2",
      "title": "Dave's team's library fundraising result",
      "content": "Dave's team raised $1,200 for the children's library. The library emailed them today (May 15, 2022) and said the donation would let it buy about 80 books. Calvin said the fundraising made the charity run more meaningful and that the children would really benefit.",
      "turn_ids": ["D1:3", "D1:4", "D1:5"]
    },
    {
      "contextfact_id": "CF3",
      "title": "Calvin's graphic-design course enrollment",
      "content": "Calvin enrolled in an evening graphic-design course on Tuesday (May 10, 2022) because he wants to design websites for nonprofits. The course lasts eight weeks, with a website for a local food pantry as its final project. Calvin is nervous about balancing it with weekend shifts. Dave thought the course suited Calvin's creativity, found the website project meaningful, and hoped to see it when finished. Calvin said Dave's support made him feel more confident.",
      "turn_ids": ["D1:4", "D1:5", "D1:6", "D1:7", "D1:8"]
    }
  ],
  "entities": [
    {
      "name": "Dave's first charity run",
      "description": "The charity run Dave completed on May 8, 2022.",
      "contextfact_ids": ["CF1", "CF2"]
    },
    {
      "name": "Dave's team",
      "description": "Dave's charity-run team, which raised money for the children's library.",
      "contextfact_ids": ["CF1", "CF2"]
    },
    {
      "name": "children's library",
      "description": "The library receiving Dave's team's fundraising donation.",
      "contextfact_ids": ["CF2"]
    },
    {
      "name": "evening graphic-design course",
      "description": "The eight-week course Calvin enrolled in to pursue design for nonprofits.",
      "contextfact_ids": ["CF3"]
    },
    {
      "name": "food-pantry website",
      "description": "The website for a local food pantry assigned as Calvin's course final project.",
      "contextfact_ids": ["CF3"]
    },
    {
      "name": "local food pantry",
      "description": "The food pantry for which Calvin's course final project will create a website.",
      "contextfact_ids": ["CF3"]
    }
  ]
}
```

# Example 2: Distinct focuses within one theme

## Input

SPEAKERS: Maya, Leo
CONVERSATION DATE: Sunday, October 9, 2022

D2:1 Maya: I completed my first overnight shift at the hospital last Friday (October 7, 2022).
It was hectic, but I handled it better than I expected.
D2:2 Leo: That's a big milestone! I'm proud of you. I sent in an application
for an evening photography course yesterday (October 8, 2022). The instructor is Elena.
D2:3 Maya: That course sounds perfect for you. The shift made me realize
I need to take my sleep more seriously.
D2:4 Leo: That makes sense. Working overnight must change how you think
about rest. Have you changed anything?
D2:5 Maya: I've started putting my phone away at 10 p.m. and preparing
my meals the night before. The routine makes me feel less rushed before work.
D2:6 Leo: That sounds sensible. If my application is accepted, the course
starts next month (November 2022). I want to learn night photography.
D2:7 Maya: I hope you get in! Planning ahead also makes me feel more confident
about my next overnight shift.
D2:8 Leo: I'm glad we keep encouraging each other. Having you in my corner
makes new challenges less intimidating. Anyway, I need to catch the bus.
D2:9 Maya: Your support means a lot to me too. Bye!
[IMG blip="a yellow bus parked beside a brick wall" query="city bus"]

## Output

```json
{
  "contextfacts": [
    {
      "contextfact_id": "CF1",
      "title": "Maya's first overnight hospital shift",
      "content": "Maya completed her first overnight shift at the hospital last Friday (October 7, 2022). It was hectic, but she handled it better than expected. Leo considered it a big milestone and said he was proud of her.",
      "turn_ids": ["D2:1", "D2:2"]
    },
    {
      "contextfact_id": "CF2",
      "title": "Leo's photography course application",
      "content": "Leo applied for an evening photography course yesterday (October 8, 2022). The instructor is Elena. If accepted, the course starts next month (November 2022). He wants to learn night photography. Maya thought the course suited him and hoped he would get in.",
      "turn_ids": ["D2:2", "D2:3", "D2:6", "D2:7"]
    },
    {
      "contextfact_id": "CF3",
      "title": "Maya's realization about sleep",
      "content": "Maya's first overnight hospital shift made her realize she needs to take her sleep more seriously. Leo thought that made sense and said overnight work must change how she thinks about rest.",
      "turn_ids": ["D2:1", "D2:3", "D2:4"]
    },
    {
      "contextfact_id": "CF4",
      "title": "Maya's new evening routine",
      "content": "Maya has started putting her phone away at 10 p.m. and preparing meals the night before. The routine makes her less rushed before work and more confident about her next overnight shift. Leo thought it sounded sensible.",
      "turn_ids": ["D2:5", "D2:6", "D2:7"]
    },
    {
      "contextfact_id": "CF5",
      "title": "Leo and Maya's mutual encouragement",
      "content": "Leo is glad he and Maya keep encouraging each other and said having her in his corner makes new challenges less intimidating. Maya said Leo's support means a lot to her too.",
      "turn_ids": ["D2:8", "D2:9"]
    }
  ],
  "entities": [
    {
      "name": "Maya's first overnight hospital shift",
      "description": "The first overnight hospital shift Maya completed on October 7, 2022.",
      "contextfact_ids": ["CF1", "CF3"]
    },
    {
      "name": "evening photography course",
      "description": "The course Leo applied for, hoping to learn night photography.",
      "contextfact_ids": ["CF2"]
    },
    {
      "name": "Elena",
      "description": "The instructor of the evening photography course Leo applied for.",
      "contextfact_ids": ["CF2"]
    },
    {
      "name": "Maya's sleep",
      "description": "Rest Maya wants to prioritize after her overnight shift.",
      "contextfact_ids": ["CF3"]
    },
    {
      "name": "Maya's evening routine",
      "description": "Maya's new preparation routine for feeling less rushed before work.",
      "contextfact_ids": ["CF4"]
    },
    {
      "name": "Maya's next overnight shift",
      "description": "The upcoming overnight shift Maya feels more confident about after planning ahead.",
      "contextfact_ids": ["CF4"]
    }
  ]
}
```

# Actual Session

## Participants

{PARTICIPANTS}

## Conversation Date

{SESSION_TIME}

## Raw Turns

{TURNS}

