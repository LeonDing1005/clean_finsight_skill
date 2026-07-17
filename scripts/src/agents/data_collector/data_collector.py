import json
from typing import List, Dict, Any, Tuple
import asyncio
from src.agents.base_agent import BaseAgent
from src.agents import DeepSearchAgent
from src.tools import Tool, ToolResult, get_tool_categories, get_tool_by_name


class DataCollector(BaseAgent):
    AGENT_NAME = 'data_collector'
    AGENT_DESCRIPTION = 'a agent that can collect data from the internet and variable apis'
    NECESSARY_KEYS = ['task']
    def __init__(
        self,
        config,
        tools = [],
        use_llm_name: str = "deepseek-chat",
        enable_code = False,
        memory = None,
        agent_id: str = None
    ):
        super().__init__(
            config=config,
            tools=tools,
            use_llm_name=use_llm_name,
            enable_code=enable_code,
            memory=memory,
            agent_id=agent_id
        )
        # Load prompts using the new YAML-based loader
        from src.utils.prompt_loader import get_prompt_loader
        
        self.prompt_loader = get_prompt_loader('data_collector', report_type='general')
        self.DATA_COLLECT_PROMPT = self.prompt_loader.get_prompt('data_collect')
        
        self.collected_data_list: List[ToolResult] = []
        if self.tools == []:
            self._set_default_tools()
        

    def _set_default_tools(self):
        """
        Attach default tools (search agent + API wrappers).
        """
        tool_list = []
        # Include the deep-search agent (sharing the same memory)
        tool_list.append(DeepSearchAgent(config=self.config, use_llm_name=self.use_llm_name, memory=self.memory))
        # Attach other API tools
        for tool_type, tool_name_list in get_tool_categories().items():
            if tool_type == 'web':
                continue
            for tool_name in tool_name_list:
                tool_instance = get_tool_by_name(tool_name)()
                tool_list.append(tool_instance)
        for tool in tool_list:
            self.memory.add_dependency(tool.id, self.id)
        self.tools = tool_list
        try:
            self.logger.info(f"Initialized default tools: total {len(tool_list)} items")
        except Exception:
            pass
        

    async def _prepare_executor(self):
        if not self.enable_code:
            return
        # Expose helper functions to the code executor for LLM-generated code
        self.code_executor.set_variable("call_tool", self._agent_tool_function)
        self.code_executor.set_variable("save_result", self._save_result)

    def _record_tool_result(self, item: ToolResult):
        """Record a tool result once in both the agent result and shared memory."""
        def already_recorded(collection):
            return any(existing is item for existing in collection)

        if not already_recorded(self.collected_data_list):
            self.collected_data_list.append(item)
        if not already_recorded(self.memory.data):
            self.memory.add_data(item)

    def _save_result(self, var: Any, result_name: str, result_description: str, data_source: str):
        """Persist execution results into self.collected_data_list."""
        self._record_tool_result(ToolResult(
            name=result_name,
            description=result_description,
            data=var,
            source=data_source
        ))
        try:
            self.logger.info(f"Saved collect result: {result_name} (source={data_source})")
        except Exception:
            pass

    def _resolve_tool(self, tool_name: str):
        for tool in self.tools:
            if isinstance(tool, Tool) and tool.name == tool_name:
                return tool
            if isinstance(tool, BaseAgent) and tool.AGENT_NAME == tool_name:
                return tool
        return None

    async def _acquire_tool_rate_limit(self, target_tool, tool_name: str):
        rate_limiter = getattr(self.config, "rate_limiter", None)
        if rate_limiter is None:
            return
        service = "financial_apis"
        tool_type = getattr(target_tool, "type", "")
        lowered = tool_name.lower()
        if "search" in lowered or "web" in lowered or "web" in tool_type:
            service = "search_engines"
        elif "fred" in lowered:
            service = "fred_api"
        elif "us" in lowered:
            service = "yfinance"
        await rate_limiter.acquire(service)

    async def _handle_tool_call_action(self, action_content: str):
        """Execute a declared tool with JSON arguments, without arbitrary code."""
        try:
            payload = json.loads(action_content)
        except (TypeError, json.JSONDecodeError) as exc:
            return {
                "action": "tool_call",
                "action_content": action_content,
                "result": f"Invalid tool-call JSON: {exc}. Return one JSON object only.",
                "continue": True,
            }

        if not isinstance(payload, dict):
            error = "Tool-call payload must be a JSON object."
        else:
            tool_name = payload.get("tool_name")
            arguments = payload.get("arguments", {})
            if not isinstance(tool_name, str) or not tool_name.strip():
                error = "tool_name must be a non-empty string."
            elif not isinstance(arguments, dict):
                error = "arguments must be a JSON object."
            else:
                error = None
        if error:
            return {
                "action": "tool_call",
                "action_content": action_content,
                "result": error,
                "continue": True,
            }

        tool_name = tool_name.strip()
        target_tool = self._resolve_tool(tool_name)
        if target_tool is None:
            available = [
                tool.name if isinstance(tool, Tool) else tool.AGENT_NAME
                for tool in self.tools
            ]
            return {
                "action": "tool_call",
                "action_content": action_content,
                "result": f"Unknown tool '{tool_name}'. Available tools: {available}",
                "continue": True,
            }

        try:
            await self._acquire_tool_rate_limit(target_tool, tool_name)
            before_count = len(self.memory.data)
            if isinstance(target_tool, BaseAgent):
                agent_input = dict(arguments)
                agent_input.setdefault("task", self.current_task_data["task"])
                response = await target_tool.async_run(input_data=agent_input, resume=False)
                for item in self.memory.data[before_count:]:
                    if isinstance(item, ToolResult):
                        self._record_tool_result(item)
                display = str(response.get("final_result", response))[:20000]
                log_output = response
            else:
                response = await target_tool.api_function(**arguments)
                if not isinstance(response, list):
                    raise TypeError(
                        f"Tool '{tool_name}' returned {type(response).__name__}; expected a list."
                    )
                tool_results = [item for item in response if isinstance(item, ToolResult)]
                if len(tool_results) != len(response):
                    raise TypeError(f"Tool '{tool_name}' returned a non-ToolResult item.")
                for item in tool_results:
                    self._record_tool_result(item)
                display = "\n\n".join(str(item) for item in tool_results) or "No results returned."
                log_output = tool_results

            self.memory.add_log(
                target_tool.id,
                target_tool.type,
                arguments,
                log_output,
                error=False,
                note=f"Structured tool call {tool_name} executed successfully",
            )
            return {
                "action": "tool_call",
                "action_content": action_content,
                "result": f"Tool '{tool_name}' completed. Results were saved automatically.\n\n{display}",
                "continue": True,
            }
        except Exception as exc:
            self.logger.error(f"Structured tool call {tool_name} failed: {exc}", exc_info=True)
            self.memory.add_log(
                self.id,
                getattr(target_tool, "type", "tool"),
                arguments,
                [],
                error=True,
                note=f"Structured tool call {tool_name} failed: {exc}",
            )
            return {
                "action": "tool_call",
                "action_content": action_content,
                "result": f"Tool '{tool_name}' failed: {exc}. Check the parameters and retry.",
                "continue": True,
            }

    def _get_api_descriptions(self) -> str:
        descriptions = [
            "Call one tool with <tool_call> JSON. Results and sources are saved automatically.",
            'Format: <tool_call>{"tool_name":"name","arguments":{"parameter":"value"}}</tool_call>',
            "Available tools:",
        ]
        for tool in self.tools:
            if isinstance(tool, Tool):
                descriptions.append(
                    f"- Tool: {tool.name}\nDescription: {tool.description}\nParameters: {tool.parameters}"
                )
            elif isinstance(tool, BaseAgent):
                descriptions.append(
                    f"- Tool: {tool.AGENT_NAME}\nDescription: {tool.AGENT_DESCRIPTION}"
                )
        return "\n\n".join(descriptions)
    
    async def _prepare_init_prompt(self, input_data: dict) -> list[dict]:
        task = input_data.get('task')
        if not task:
            raise ValueError("Input data must contain a 'task' key.")
        
        # Get target language from config
        target_language = self.config.config.get('language', 'zh')
        language_mapping = {
            'zh': 'Chinese (中文)',
            'en': 'English'
        }
        target_language_name = language_mapping.get(target_language, target_language)
        
        # Extract research target from task
        target_name = self.config.config.get('target_name', '')
        stock_code = self.config.config.get('stock_code', '')
        research_target = f"{target_name} (ticker: {stock_code})" if stock_code else target_name
            
        return [{
            "role": "user",
            "content": self.DATA_COLLECT_PROMPT.format(
                api_descriptions=self._get_api_descriptions(),
                code_execution_guidance=(
                    "Generated Python is enabled for this trusted run. Prefer <tool_call>; "
                    "use <execute> only when a tool result needs in-memory transformation, "
                    "then persist the transformed value with "
                    "save_result(value, result_name, result_description, source_name_and_url)."
                    if self.enable_code else
                    "Generated Python is disabled for this run. Use <tool_call> for every data request; "
                    "do not emit <execute>."
                ),
                current_time=self.current_time,
                task=task,
                target_language=target_language_name,
                research_target=research_target
            )
        }]
    

    async def async_run(
        self, 
        input_data: dict, 
        max_iterations: int = 10,
        stop_words: list[str] = [],
        echo=False,
        resume: bool = True,
        checkpoint_name: str = 'latest.pkl',
        # stop_words: list[str] = ["</execute>", "</final_result>"]
    ) -> dict:
        # Reset collected-data cache for each run
        self.collected_data_list = []
        self.logger.info(f"DataCollector started: task={input_data.get('task','')} resume={resume}")
        await self._prepare_executor()
        run_result = await super().async_run(
            input_data=input_data,
            max_iterations=max_iterations,
            stop_words=stop_words,
            echo=echo,
            resume=resume,
            checkpoint_name=checkpoint_name,
        )
        run_result['collected_data_list'] = self.collected_data_list
        self.logger.info(f"Successfully save {len(self.collected_data_list)} items to memory")
        self.memory.add_log(
            id=self.id,
            type=self.type,
            input_data=input_data,
            output_data=self.collected_data_list,
            error=False,
            note=f"DataCollector finished: collected={len(self.collected_data_list)} items"
        )
        self.logger.info(f"DataCollector finished: collected={len(self.collected_data_list)} items")
        self.memory.save()
        return run_result

    def _get_persist_extra_state(self) -> Dict[str, Any]:
        return {
            'collected_data_list': self.collected_data_list,
        }

    def _load_persist_extra_state(self, state: Dict[str, Any]):
        self.collected_data_list = state.get('collected_data_list', [])
