"""
Ollama Integration for DOES Framework

Handles model loading/unloading and invocation for Builder and Villain nodes.
Manages system memory pressure on hardware-constrained environments.
"""

import json
import subprocess
import logging
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)

# Ollama API endpoint (default local)
OLLAMA_API = "http://localhost:11434"
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_API}/api/generate"


class OllamaNodeManager:
    """Manages Ollama model lifecycle: load, invoke, unload."""

    def __init__(self, base_url: str = OLLAMA_API):
        self.base_url = base_url
        self.active_model = None

    def is_running(self) -> bool:
        """Check if Ollama service is running."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama service check failed: {e}")
            return False

    def list_models(self) -> list:
        """Get list of available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m["name"] for m in models]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
        return []

    def invoke_model(
        self, model_name: str, prompt: str, system_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Invoke a model with the given prompt.

        Args:
            model_name: Name of the model in Ollama (e.g., 'qwen', 'villain-node')
            prompt: The prompt to send
            system_prompt: Optional system prompt override

        Returns:
            Model response text, or None on failure
        """
        try:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
            }

            if system_prompt:
                payload["system"] = system_prompt

            response = requests.post(OLLAMA_GENERATE_ENDPOINT, json=payload, timeout=300)

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                logger.error(f"Model invocation failed: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Model invocation timed out for {model_name}")
            return None
        except Exception as e:
            logger.error(f"Model invocation error: {e}")
            return None

    def invoke_model_json(
        self, model_name: str, prompt: str, system_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Invoke a model and expect JSON response.

        Parses the response as JSON and returns the parsed object.
        """
        response = self.invoke_model(model_name, prompt, system_prompt)

        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                logger.warning(f"Failed to parse JSON response from {model_name}")
                # Attempt to find JSON in the response
                import re

                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

        return None

    def pull_model(self, model_name: str) -> bool:
        """Download/pull a model from Ollama registry."""
        try:
            logger.info(f"Pulling model: {model_name}")
            response = requests.post(
                f"{self.base_url}/api/pull", json={"name": model_name}, timeout=3600
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False

    def create_model(self, name: str, modelfile_path: str) -> bool:
        """
        Create a custom model from a Modelfile.

        This corresponds to: ollama create <name> -f <modelfile_path>
        """
        try:
            logger.info(f"Creating model {name} from {modelfile_path}")

            # Read the Modelfile
            with open(modelfile_path, "r") as f:
                modelfile_content = f.read()

            # Ollama API expects the modelfile as raw content
            response = requests.post(
                f"{self.base_url}/api/create",
                json={"name": name, "modelfile": modelfile_content},
                timeout=3600,
            )

            if response.status_code == 200:
                logger.info(f"Successfully created model: {name}")
                return True
            else:
                logger.error(
                    f"Failed to create model {name}: {response.status_code} {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Model creation error: {e}")
            return False

    def stop_model(self, model_name: str) -> bool:
        """Stop/unload a model from memory."""
        try:
            logger.info(f"Stopping model: {model_name}")
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=30,
            )
            self.active_model = None
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to stop model {model_name}: {e}")
            return False


# Singleton instance
_ollama_manager = None


def get_ollama_manager() -> OllamaNodeManager:
    """Get or create the Ollama manager singleton."""
    global _ollama_manager
    if _ollama_manager is None:
        _ollama_manager = OllamaNodeManager()
    return _ollama_manager


def invoke_builder(
    prompt: str, system_prompt: Optional[str] = None, model_name: str = "qwen"
) -> Optional[str]:
    """Convenience function to invoke Builder node."""
    manager = get_ollama_manager()
    return manager.invoke_model(model_name, prompt, system_prompt)


def invoke_villain(
    prompt: str, system_prompt: Optional[str] = None, model_name: str = "villain-node"
) -> Optional[Dict[str, Any]]:
    """Convenience function to invoke Villain node with JSON response."""
    manager = get_ollama_manager()
    return manager.invoke_model_json(model_name, prompt, system_prompt)


__all__ = [
    "OllamaNodeManager",
    "get_ollama_manager",
    "invoke_builder",
    "invoke_villain",
]
