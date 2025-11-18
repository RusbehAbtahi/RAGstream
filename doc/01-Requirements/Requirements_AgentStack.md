# Requirements_AgentStack.md

1. Purpose and scope

---

This document specifies the “Agent Stack” used by all LLM-using agents in RAGstream.

The Agent Stack covers:

* AgentFactory (agent_factory.py)
* AgentPrompt (agent_prompt.py)
* llm_client (llm_client.py)

The Controller and each Agent (e.g. A2 PromptShaper, PreProcessing, A3, A4, A5) are mentioned only where needed to define interfaces, but their detailed requirements live elsewhere.

The goals of this stack are:

* Neutral, stateless behavior (no hidden state, no A2-specific logic inside AgentFactory / AgentPrompt / llm_client).
* Agents defined as **data** (JSON configs) instead of hard-coded logic.
* Support for three agent types: **Chooser**, **Writer**, **Extractor**.
* Clean separation of concerns:

  * Agent = domain logic and deterministic post-processing
  * AgentFactory = config loader + validation + AgentPrompt construction
  * AgentPrompt = neutral prompt composer + output validator
  * llm_client = low-level LLM call

A2 PromptShaper is used as the running example, but the same stack must work for PreProcessing, A3, A4, A5 and future agents.

2. High-level data flow (A2 example)

---

Example: A2 PromptShaper is called by the Controller with a SuperPrompt that already contains `task`, `purpose`, `context`.

The A2 data flow using the Agent Stack:

1. Controller

   * Calls `A2.run(superprompt, version="v1")`.
   * Does not know anything about agent configs, AgentFactory, AgentPrompt, or llm_client.

2. A2 (agent code)

   * Extracts from `superprompt` the fields it wants to send to the LLM, e.g.:

     * `task`
     * `purpose`
     * `context`

   * Builds an `input_payload` dict:

     ```python
     input_payload = {
         "task": superprompt.task,
         "purpose": superprompt.purpose,
         "context": superprompt.context,
     }
     ```

   * Calls AgentFactory:

     ```python
     agent_prompt = AgentFactory.create(
         agent_name="A2",
         version="v1",
         input_payload=input_payload,
     )
     ```

   * Calls AgentPrompt to compose the prompt:

     ```python
     messages, response_format = agent_prompt.compose(input_payload)
     ```

   * Calls llm_client:

     ```python
     llm_raw_output = llm_client.call(
         model=agent_prompt.model_name,
         messages=messages,
         response_format=response_format,
         temperature=agent_prompt.temperature,
     )
     ```

   * Uses AgentPrompt to validate / parse the output:

     ```python
     labels = agent_prompt.parse_and_validate(llm_raw_output)
     # labels: dict with system, audience, tone, response_depth, confidence
     ```

   * Runs deterministic checks and logging, updates SuperPrompt with the new labels, and returns to the Controller.

3. AgentFactory

   * Loads the JSON config for agent `"A2"` and version `"v1"`.
   * Validates `input_payload` shape (required keys, types).
   * Builds a configured AgentPrompt instance and returns it to A2.

4. AgentPrompt

   * Holds the agent’s **configuration** (from JSON): mode (Chooser/Writer/Extractor), system text, purpose text, enums, response schema, model name, temperature, etc.
   * Is **neutral**: no A2-specific or agent-specific logic.
   * When `compose(input_payload)` is called, it produces the LLM prompt (SYSTEM + USER messages) and the JSON schema (`response_format`).
   * When `parse_and_validate(raw_output)` is called, it validates the LLM’s JSON against enums / schema / defaults and returns a clean Python dict.

5. llm_client

   * Low-level wrapper around the LLM API (OpenAI for now).
   * Only knows about `model`, `messages`, `response_format` (JSON schema), and standard parameters like temperature.
   * Does not know anything about agents or AgentPrompt.

3) Agent configuration data (JSON)

---

3.1. Storage format

* All agent configurations MUST be stored as **JSON** files.
* The primary reason: JSON is native to your LLM structured output, to OpenAI APIs, and to Python dicts; it avoids an extra format conversion layer.
* YAML is NOT required at this stage and MUST NOT be used for agent configs unless explicitly introduced later by a separate decision.

3.2. File layout (within RAGstream project)

* Agent config files SHOULD live under a dedicated folder, for example:

  * `config/agents/{agent_name}/{version}.json`

  Examples:

  * `config/agents/A2/v1.json`
  * `config/agents/PreProcessing/v1.json`
  * `config/agents/A3/v1.json`

* The exact path construction is the responsibility of AgentFactory; agents (A2, etc.) must not hard-code file paths.

3.3. AgentConfig JSON schema (conceptual)

Each agent config JSON MUST follow this conceptual structure:

```json
{
  "agent_name": "A2",
  "version": "v1",

  "mode": "Chooser",         // Chooser | Writer | Extractor

  "system_text": "You are A2 PromptShaper. ...",
  "purpose_text": "You must inspect task/purpose/context and choose labels for system, audience, tone, response_depth, confidence.",

  "output_schema": {
    "type": "object",
    "required": ["system", "audience", "tone", "response_depth", "confidence"],
    "properties": {
      "system": {
        "type": "string",
        "enum": ["Python_Programmer", "AWS_Architect", "Friend"]
      },
      "audience": {
        "type": "string",
        "enum": ["Developer", "Manager", "Friend", "Self"]
      },
      "tone": {
        "type": "string",
        "enum": ["direct", "friendly", "formal"]
      },
      "response_depth": {
        "type": "string",
        "enum": ["short", "detailed", "exhaustive"]
      },
      "confidence": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      }
    }
  },

  "enums": {
    "system": ["Python_Programmer", "AWS_Architect", "Friend"],
    "audience": ["Developer", "Manager", "Friend", "Self"],
    "tone": ["direct", "friendly", "formal"],
    "response_depth": ["short", "detailed", "exhaustive"],
    "confidence": ["low", "medium", "high"]
  },

  "defaults": {
    "tone": "direct",
    "response_depth": "detailed",
    "confidence": "medium"
  },

  "model_name": "gpt-4.1-mini",
  "temperature": 0.0,
  "max_output_tokens": 256
}
```

Requirements:

* `agent_name` and `version` MUST match what the Agent passes to AgentFactory.

* `mode` MUST be one of `"Chooser"`, `"Writer"`, `"Extractor"`.

  * **Chooser:** LLM selects one or more values from enums for each output field.
  * **Writer:** LLM fills text fields (e.g. summaries, explanations) according to schema; enums may be absent or minimal.
  * **Extractor:** LLM extracts structured information from input and maps it into schema fields (e.g. named entities, slots).

* `system_text` and `purpose_text` are pure text; they define behavior but contain no code.

* `output_schema` defines the JSON schema to be used as `response_format` for the LLM.

* `enums` MUST be consistent with `output_schema.properties[<field>].enum` where applicable.

* `defaults` MAY provide fallback values if a field is missing in the LLM output.

* `model_name` MUST match an OpenAI chat model name (or a fine-tuned model id).

* `temperature` and `max_output_tokens` are basic numeric parameters; no further tuning knobs are required at this stage.

Future extension: if you later need multiple providers (OpenAI, local TinyLlama, etc.), a `provider` field can be introduced, but it is not part of this initial requirement.

4. AgentFactory (agent_factory.py)

---

4.1. Purpose

AgentFactory is responsible for:

* Mapping `(agent_name, version)` to the correct JSON config file.
* Loading and parsing the JSON into an internal `AgentConfig` structure.
* Validating the config’s internal consistency (e.g. enums vs schema).
* Validating that the `input_payload` provided by the Agent matches what the config expects (required keys, types).
* Constructing and returning a properly configured AgentPrompt instance.

AgentFactory MUST NOT:

* Contain any agent-specific logic (no A2-only special cases).
* Call llm_client directly.
* Compose prompts by itself.

4.2. Statelessness

* AgentFactory MUST be stateless. Each call to `create(...)` must depend only on its arguments and the JSON file contents.
* It MUST NOT cache mutable state between calls; if caching is later added (e.g. config cache), it must be read-only and transparent to callers.

4.3. Public interface

AgentFactory MUST provide at least one public function or class method with this conceptual signature:

```python
AgentFactory.create(
    agent_name: str,
    version: str,
    input_payload: dict
) -> AgentPrompt
```

Behavior:

1. Resolve the config path:

   * Deduce `config/agents/{agent_name}/{version}.json` (or similar convention).
   * If the file does not exist, raise a clear error (e.g. `UnknownAgentConfigError`).

2. Load and parse JSON:

   * Parse JSON to Python dict.
   * Verify required top-level keys: `agent_name`, `version`, `mode`, `system_text`, `purpose_text`, `output_schema`, `model_name`.
   * Verify that `agent_name` and `version` inside JSON match the inputs.

3. Validate enums vs schema:

   * For each field in `enums`, check that the schema has a property with matching enum list (if enum defined).
   * For fields in `output_schema` with `enum`, ensure they appear in `enums`.

4. Validate input_payload shape (shallow check):

   * For this requirement, AgentFactory SHOULD verify that `input_payload` is a dict.
   * Optionally, the config may define expected input keys (e.g. `input_keys: ["task", "purpose", "context"]`). If present, AgentFactory SHOULD check that they exist.
   * Semantic validation (e.g. “task must be nonempty string”) stays in the Agent.

5. Construct AgentPrompt:

   * Create an AgentPrompt instance with:

     * agent_name
     * version
     * mode
     * system_text
     * purpose_text
     * output_schema
     * enums
     * defaults
     * model_name
     * temperature
     * max_output_tokens

   * Return this AgentPrompt instance to the Agent.

5) AgentPrompt (agent_prompt.py)

---

5.1. Purpose

AgentPrompt is the **neutral prompt engine**.

Responsibilities:

* Hold the agent configuration (as passed from AgentFactory).
* Compose the LLM prompt (SYSTEM + USER message) for a given `input_payload`, using a fixed neutral pattern.
* Provide the `response_format` (JSON schema) for structured output.
* Parse and validate the LLM’s raw output into a clean Python dict, enforcing enums, defaults, and required fields.

AgentPrompt MUST NOT:

* Know which concrete agent (A2, PreProcessing, etc.) is calling it, beyond the strings in config.
* Contain any logic specific to A2 or any other agent.
* Perform retrieval, reranking, or any pipeline-level decisions.
* Call llm_client directly.

5.2. Statelessness and neutrality

* AgentPrompt instances are **configuration holders**, not conversation memories.
* They MUST NOT store any per-call state (no incremental history).
* All per-call data (input_payload and raw output) MUST be passed as parameters to methods.
* AgentPrompt MUST use the same composition pattern for all agents; the only differences come from the config fields.

5.3. Configuration fields

An AgentPrompt instance MUST hold the following configuration:

* `agent_name: str`
* `version: str`
* `mode: str` (Chooser | Writer | Extractor)
* `system_text: str`
* `purpose_text: str`
* `output_schema: dict` (JSON schema)
* `enums: dict[str, list[str]]`
* `defaults: dict[str, Any]` (may be empty)
* `model_name: str`
* `temperature: float`
* `max_output_tokens: int`

These should be passed from AgentFactory, not modified later.

5.4. Public methods

AgentPrompt MUST provide at least two public methods:

### 5.4.1. compose(input_payload: dict) -> (messages: list[dict], response_format: dict)

Responsibilities:

* Build the SYSTEM message text by combining:

  * `system_text`
  * `purpose_text`
  * `agent_name` and `version` (for traceability)
  * A fixed instruction to return only JSON that matches `output_schema`.

* Build the USER message text using a neutral pattern:

  * List all entries in `input_payload` as `key = "value"` lines, in a simple readable block.

  * Based on `mode` and `enums`:

    * **Chooser:**
      For each field in `enums`, tell the LLM:
      “Choose `<field>` from [list of allowed values].”

    * **Writer:**
      Use `output_schema` to list the fields that must be filled with text; instruct the LLM to “fill each field with appropriate text following the purpose.”

    * **Extractor:**
      Use `output_schema` to instruct the LLM to extract or map information from `input_payload` into the schema fields.

  * End with a fixed sentence such as:
    “Reply with a single JSON object only, no extra text, matching the schema.”

* Return:

  * `messages`: list of dicts for llm_client, for example:

    ```python
    [
      {"role": "system", "content": "...constructed SYSTEM text..."},
      {"role": "user", "content": "...constructed USER text..."}
    ]
    ```

  * `response_format`: the `output_schema` dict (or the appropriate OpenAI structured output wrapper, if needed).

### 5.4.2. parse_and_validate(raw_output: Any) -> dict

Input:

* `raw_output` is the raw LLM completion object or the JSON content (depending on llm_client design).

Responsibilities:

* Extract the JSON object from the LLM response.

* Validate against `output_schema`:

  * All required fields are present.
  * No type mismatches (string vs number, etc.).
  * For fields with enums, the value MUST be in the allowed list.
  * Fill missing fields from `defaults` if defined.

* Return a clean Python dict representing the agent output.

If validation fails:

* Raise a clear error (e.g. `AgentPromptValidationError`) or return a structured error object that A2 can handle deterministically.

6. llm_client (llm_client.py)

---

6.1. Purpose

llm_client is the lowest-level LLM access layer.

Responsibilities:

* Provide a simple function to call the LLM with:

  * `model_name`
  * `messages`
  * `response_format` (JSON schema)
  * basic parameters such as `temperature` and `max_tokens`

* Hide OpenAI API details from agents, AgentPrompt, and AgentFactory.

* Return the raw completion object or parsed JSON, depending on design.

llm_client MUST NOT:

* Know about agents, AgentPrompt, SuperPrompt, or pipeline steps.
* Interpret system_text, enums, or any config semantics.
* Do prompt composition.

6.2. Current provider and future-proofing

* For now, llm_client MUST call **OpenAI chat models** (e.g. `gpt-4.1-mini`, or a fine-tuned model ID).

* It MUST support both:

  * base models (e.g. `gpt-4.1-mini`)
  * fine-tuned models (e.g. `ft:gpt-4.1-mini-2025-04-14:personal:a2-promptshaper-v1:XXXX`)

* The interface MUST be designed so that, later, additional backends can be implemented behind the same function signature without changing A2, AgentFactory, or AgentPrompt.

6.3. Public interface

llm_client MUST provide at least one function with this conceptual signature:

```python
llm_client.call(
    model: str,
    messages: list[dict],
    response_format: dict | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> Any
```

Behavior:

* Build the appropriate payload for the OpenAI Chat Completions / Responses API, including:

  * `model`
  * `messages`
  * `response_format` (for structured JSON output, if used)
  * `temperature`
  * `max_tokens`

* Send the request and return the raw response.

* It MAY optionally decode the JSON if the API returns a JSON object directly; if so, this behavior must be clearly documented so AgentPrompt knows what to expect.

7. Non-functional requirements

---

7.1. Determinism and testability

* AgentFactory, AgentPrompt, and llm_client MUST be deterministic given the same inputs and config.
* No timestamps, randomness (except the LLM itself), or hidden global state may influence their behavior.
* Unit tests MUST be possible for each layer:

  * AgentFactory: config validation, error handling.
  * AgentPrompt: composition and validation logic using fake inputs and fake LLM outputs.
  * llm_client: can be tested via mocking the HTTP layer.

7.2. Extensibility and versioning

* Adding a new agent or version MUST require creating a new JSON file only; existing code in AgentFactory / AgentPrompt / llm_client should remain unchanged.
* If output schema changes in an incompatible way, a new `version` MUST be introduced (e.g. `"v2"`), and the old JSON MUST NOT be silently overwritten.

7.3. Logging (minimal expectations)

* Agents (e.g. A2) are responsible for logging their own inputs and outputs.
* AgentStack components SHOULD provide enough structured data so that A2 can log:

  * `agent_name`, `version`, `model_name`
  * composed SYSTEM/USER messages (if desired)
  * raw LLM output and validated output

llm_client itself SHOULD at least log errors and basic metrics (e.g. token usage) where available, but detailed logging requirements can be defined in a separate document.

---

This completes the requirements for the Agent Stack: AgentFactory, AgentPrompt, and llm_client.
