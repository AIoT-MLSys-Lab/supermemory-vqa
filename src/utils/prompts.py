"""
Prompt management utilities for loading and managing annotation prompts
Supports both Python dataclass-based prompts and legacy JSON prompts
"""
import json
import logging
import os
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..',
                           'prompts')


class PromptDefinition:
    """Represents a prompt definition - wrapper for both JSON and dataclass
    prompts"""

    def __init__(self, prompt_obj: Any):
        """
        Initialize from either a dataclass prompt or legacy data dict
        
        Args:
            prompt_obj: Either a PromptDefinitionBase instance or dict with
            prompt data
        """
        # Check if it's a dataclass-based prompt
        if hasattr(prompt_obj, 'render') and hasattr(prompt_obj,
                                                     'get_parameters'):
            # It's a dataclass prompt
            self.id = prompt_obj.id
            self.name = prompt_obj.name
            self.description = prompt_obj.description
            self.version = prompt_obj.version
            self._prompt_obj = prompt_obj
            self.input_parameters = {
                param.name: param.to_dict()
                for param in prompt_obj.get_parameters()
            }
            self.prompt_template = prompt_obj.get_template()
            self.output_schema = prompt_obj.get_output_schema()
            self.is_dataclass = True
        else:
            # Legacy dict-based prompt
            self.filepath = prompt_obj.get('filepath', '')
            self.name = prompt_obj.get('name', 'Unnamed Prompt')
            self.description = prompt_obj.get('description', '')
            self.version = prompt_obj.get('version', '1.0')
            self.prompt_template = prompt_obj.get('prompt_template', '')
            self.input_parameters = prompt_obj.get('input_parameters', {})
            self.output_schema = prompt_obj.get('output_schema', {})
            self.id = prompt_obj.get('id', '')
            self._prompt_obj = None
            self.is_dataclass = False

    def render(self, **kwargs) -> str:
        """
        Render the prompt template with given parameters
        
        Args:
            **kwargs: Parameter values to substitute in template
            
        Returns:
            Rendered prompt string
        """
        if self.is_dataclass:
            return self._prompt_obj.render(**kwargs)

        # Legacy rendering
        params = {}
        for param_name, param_def in self.input_parameters.items():
            params[param_name] = param_def.get('default')

        params.update(kwargs)
        params['output_schema'] = json.dumps(self.output_schema, indent=2)

        try:
            return self.prompt_template.format(**params)
        except KeyError as e:
            logger.error(f"Missing parameter in prompt template: {e}")
            raise ValueError(f"Missing required parameter: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'input_parameters': self.input_parameters,
            'is_dataclass': self.is_dataclass
        }


class PromptManager:
    """Manages loading and accessing prompt definitions"""

    def __init__(self, prompts_dir: str = None):
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self.prompts: Dict[str, PromptDefinition] = {}
        self.load_all_prompts()

    def load_all_prompts(self):
        """Load all prompt definitions from both dataclasses and JSON files"""
        # First, load dataclass-based prompts
        try:
            from utils.prompt_definitions import get_all_prompts
            dataclass_prompts = get_all_prompts()
            for prompt_id, prompt_instance in dataclass_prompts.items():
                self.prompts[prompt_id] = PromptDefinition(prompt_instance)
                logger.info(
                    f"Loaded dataclass prompt: {prompt_instance.name} ("
                    f"{prompt_id})")
        except Exception as e:
            logger.error(f"Failed to load dataclass prompts: {e}")

        # Also load legacy JSON prompts for backward compatibility
        if not os.path.exists(self.prompts_dir):
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            os.makedirs(self.prompts_dir, exist_ok=True)
            return

        for filename in os.listdir(self.prompts_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.prompts_dir, filename)
                try:
                     prompt_id = os.path.splitext(os.path.basename(filepath))[0]
                     # Skip if already loaded from dataclass
                     if prompt_id not in self.prompts:
                         self.load_json_prompt(filepath)
                except Exception as e:
                     logger.error(f"Failed to load JSON prompt {filename}: {e}")

    def load_json_prompt(self, filepath: str) -> PromptDefinition:
        """Load a single prompt definition from JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        prompt_id = os.path.splitext(os.path.basename(filepath))[0]
        data['id'] = prompt_id
        data['filepath'] = filepath

        prompt = PromptDefinition(data)
        self.prompts[prompt.id] = prompt
        logger.info(f"Loaded JSON prompt: {prompt.name} ({prompt.id})")
        return prompt

    def get_prompt(self, prompt_id: str) -> PromptDefinition:
        """Get a prompt definition by ID"""
        if prompt_id not in self.prompts:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return self.prompts[prompt_id]

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List all available prompts"""
        return [prompt.to_dict() for prompt in self.prompts.values()]

    def get_default_prompt(self) -> PromptDefinition:
        """Get the default prompt (qa_annotation_v1)"""
        if 'qa_annotation_v1' in self.prompts:
            return self.prompts['qa_annotation_v1']

        if self.prompts:
            return list(self.prompts.values())[0]

        raise ValueError("No prompts available")


# Global prompt manager instance
_prompt_manager = None


def get_prompt_manager() -> PromptManager:
    """Get or create the global prompt manager instance"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
