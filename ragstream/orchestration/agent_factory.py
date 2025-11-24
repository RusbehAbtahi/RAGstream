# -*- coding: utf-8 -*-
"""
AgentFactory
============


- This is the single place where AgentPrompt objects are created from JSON configs.
- It hides all file-system details (where JSON lives, how paths are built).
- It also caches created agents, so JSON is read only once per (agent_id, version).

Usage model (high level):
- Controller creates ONE AgentFactory instance at startup.
- Each Agent (A2, A3, ...) asks this factory for its AgentPrompt:
    factory.get_agent("a2_promptshaper", "001")
- The returned AgentPrompt is then used to compose/parse LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ragstream.utils.logging import SimpleLogger
from ragstream.orchestration.agent_prompt import AgentPrompt


class AgentFactory:
    """
    Central factory for building and caching AgentPrompt instances.

    Design goals:
    - Neutral: knows nothing about A2/A3/etc. beyond their (agent_id, version).
    - File-based: loads JSON configs from data/agents/<agent_id>/<version>.json.
    - Cached: Agents are constructed once and reused for the lifetime of the factory.
    """

    def __init__(self, agents_root: Optional[Path] = None) -> None:
        """
        Initialize the factory.

        Parameters
        ----------
        agents_root:
            Optional base directory where all agent JSON configs live.
            If None, we derive it from the package layout assuming the repo root
            looks like:

                RAGstream/
                    data/
                        agents/
                            a2_promptshaper/001.json
                    ragstream/
                        orchestration/
                            agent_factory.py
                        ...

            In that case:
                repo_root = Path(__file__).resolve().parents[2]
                agents_root = repo_root / "data" / "agents"
        """
        if agents_root is None:
            # Go from ragstream/orchestration/agent_factory.py
            #   -> ragstream/
            #   -> RAGstream/ (repo root)
            repo_root = Path(__file__).resolve().parents[2]
            agents_root = repo_root / "data" / "agents"

        self.agents_root: Path = agents_root
        self._cache: Dict[Tuple[str, str], AgentPrompt] = {}

        SimpleLogger.info(f"AgentFactory initialized with agents_root={self.agents_root}")

    # ------------------------------------------------------------------
    # Internal path builder
    # ------------------------------------------------------------------

    def _build_config_path(self, agent_id: str, version: str) -> Path:
        """
        Internal helper: compute the JSON config path for a given agent_id/version.

        Example:
            agent_id = "a2_promptshaper"
            version  = "001"
        Path becomes:
            <agents_root>/a2_promptshaper/001.json
        """
        return self.agents_root / agent_id / f"{version}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_config(self, agent_id: str, version: str) -> Dict[str, Any]:
        """
        Load the raw JSON config for a given agent_id and version.

        Responsibilities:
        - Build the file path.
        - Read JSON from disk.
        - Raise a clear error if the file does not exist or is invalid.

        This method does NOT cache anything; it just returns the config dict.
        """
        cfg_path = self._build_config_path(agent_id, version)

        if not cfg_path.is_file():
            msg = f"AgentFactory: config not found for {agent_id=} {version=} at {cfg_path}"
            SimpleLogger.error(msg)
            raise FileNotFoundError(msg)

        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                config: Dict[str, Any] = json.load(f)
        except Exception as exc:
            msg = f"AgentFactory: failed to load JSON config from {cfg_path}: {exc}"
            SimpleLogger.error(msg)
            raise

        return config

    def get_agent(self, agent_id: str, version: str = "001") -> AgentPrompt:
        """
        Return an AgentPrompt instance for the given (agent_id, version).

        Responsibilities:
        - Check the in-memory cache first.
        - If not present:
            - Load the JSON config.
            - Build AgentPrompt via AgentPrompt.from_config(config).
            - Store it in the cache.
        - Always return the same AgentPrompt instance for the same key.

        This ensures:
        - We only hit the file system once per agent/version.
        - All callers share the same AgentPrompt configuration object.
        """
        key = (agent_id, version)
        if key in self._cache:
            return self._cache[key]

        config = self.load_config(agent_id, version)
        agent = AgentPrompt.from_config(config)
        self._cache[key] = agent

        SimpleLogger.info(
            f"AgentFactory: created AgentPrompt for agent_id={agent_id}, version={version}"
        )
        return agent

    def clear_cache(self) -> None:
        """
        Clear the internal cache of AgentPrompt instances.

        Why this exists:
        - Mostly for testing or advanced scenarios (e.g. live-reloading configs).
        - In normal operation you probably never call this.

        Behavior:
        - Simply empties the cache dict; no further side effects.
        """
        self._cache.clear()
        SimpleLogger.info("AgentFactory: cache cleared")
