"""Prompt loader for YAML-based prompt templates."""

import os
import yaml
import warnings
from typing import Dict, Any, Optional
from pathlib import Path


class PromptLoader:
    """Load and manage prompts from YAML configuration files."""
    
    def __init__(self, prompts_dir: str, report_type: str = "general"):
        self.prompts_dir = Path(prompts_dir)
        self.report_type = report_type
        self.prompts: Dict[str, Any] = {}
        
        if not self.prompts_dir.exists():
            raise ValueError(f"Prompts directory not found: {self.prompts_dir}")
        
        self._load_prompts()
    
    def _load_prompts(self):
        """Load prompts from YAML file based on report_type."""
        # Try multiple naming conventions in priority order
        candidate_names = [
            f"{self.report_type}_prompts.yaml",              # company_prompts.yaml
            f"financial_{self.report_type}_prompts.yaml",     # financial_company_prompts.yaml
            f"financial_prompts.yaml",                        # financial_prompts.yaml (shared)
            f"{self.report_type.split('_')[0]}_prompts.yaml", # parent type fallback
            "prompts.yaml",                                   # generic fallback
            "general_prompts.yaml",                           # ultimate fallback
        ]

        yaml_file = None
        for name in candidate_names:
            candidate = self.prompts_dir / name
            if candidate.exists():
                yaml_file = candidate
                break

        if yaml_file is None:
            raise FileNotFoundError(
                f"No prompt file found in {self.prompts_dir}. "
                f"Tried: {candidate_names}"
            )
        
        with open(yaml_file, 'r', encoding='utf-8') as f:
            self.prompts = yaml.safe_load(f) or {}
    
    def get_prompt(self, prompt_key: str, **kwargs) -> str:
        """Get a prompt template and optionally format it with kwargs."""
        if prompt_key not in self.prompts:
            # raise KeyError(
            #     f"Prompt '{prompt_key}' not found in {self.prompts_dir}. "
            #     f"Available prompts: {list(self.prompts.keys())}"
            # )
            warnings.warn(f"Prompt '{prompt_key}' not found in {self.prompts_dir}. "
                f"Available prompts: {list(self.prompts.keys())}"
            )
            return None
            
        
        prompt_template = self.prompts[prompt_key]
        
        # If kwargs provided, format the template
        if kwargs:
            try:
                return prompt_template.format(**kwargs)
            except KeyError as e:
                raise KeyError(
                    f"Missing required format parameter {e} for prompt '{prompt_key}'"
                )
        
        return prompt_template
    
    def get_all_prompts(self) -> Dict[str, str]:
        """Get all loaded prompts."""
        return self.prompts.copy()
    
    def list_available_prompts(self) -> list:
        """List all available prompt keys."""
        return list(self.prompts.keys())
    
    def reload(self, report_type: Optional[str] = None):
        """Reload prompts, optionally changing the report type."""
        if report_type:
            self.report_type = report_type
        self.prompts = {}
        self._load_prompts()
    
    @staticmethod
    def create_loader_for_agent(agent_name: str, report_type: str = "general") -> 'PromptLoader':
        """Create a PromptLoader for a specific agent."""
        # Get the absolute path to the agents directory
        current_file = Path(__file__)
        src_dir = current_file.parent.parent
        prompts_dir = src_dir / "agents" / agent_name / "prompts"
        
        return PromptLoader(str(prompts_dir), report_type=report_type)
    
    @staticmethod
    def create_loader_for_memory(report_type: str = "general") -> 'PromptLoader':
        """Create a PromptLoader for memory module."""
        # Get the absolute path to the memory directory
        current_file = Path(__file__)
        src_dir = current_file.parent.parent
        prompts_dir = src_dir / "memory" / "prompts"
        
        return PromptLoader(str(prompts_dir), report_type=report_type)


def get_prompt_loader(module_name: str, report_type: str = "general") -> PromptLoader:
    """Get a PromptLoader for any module."""
    if module_name == "memory":
        return PromptLoader.create_loader_for_memory(report_type)
    else:
        return PromptLoader.create_loader_for_agent(module_name, report_type)

