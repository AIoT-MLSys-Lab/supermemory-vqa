import matplotlib.pyplot as plt
import os
import logging
from typing import Dict, List, DefaultDict
from collections import defaultdict

logger = logging.getLogger(__name__)

class TokenTracker:
    def __init__(self):
        self.usage_records: DefaultDict[str, List[Dict[str, int]]] = defaultdict(list)

    def log_usage(self, agent_name: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0):
        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        cached_tokens = cached_tokens or 0
        self.usage_records[agent_name].append({
            'input': input_tokens,
            'output': output_tokens,
            'cached': cached_tokens
        })
        cache_pct = f" (cache: {cached_tokens / max(input_tokens, 1) * 100:.0f}%)" if cached_tokens > 0 else ""
        logger.info(f"[{agent_name}] Tokens — in: {input_tokens:,}, out: {output_tokens:,}, cached: {cached_tokens:,}{cache_pct}")

    def plot_and_save(self, output_dir: str):
        if not self.usage_records:
            logger.warning("No token usage recorded to plot.")
            return

        os.makedirs(output_dir, exist_ok=True)

        agents = list(self.usage_records.keys())
        avg_inputs = []
        avg_outputs = []
        total_inputs = []
        total_outputs = []
        total_cached = []

        for i, agent in enumerate(agents):
            records = self.usage_records[agent]
            inputs = [(r['input'] or 0) for r in records]
            outputs = [(r['output'] or 0) for r in records]
            cached = [(r.get('cached') or 0) for r in records]
            
            avg_inputs.append(sum(inputs) / len(inputs) if inputs else 0)
            avg_outputs.append(sum(outputs) / len(outputs) if outputs else 0)
            total_inputs.append(sum(inputs))
            total_outputs.append(sum(outputs))
            total_cached.append(sum(cached))

            if not inputs and not outputs:
                logger.warning(f"No token data to plot for {agent}.")
                continue

            fig, ax = plt.subplots(figsize=(8, 5))
            
            # Avoid empty sequence unpacking error for matplotlib hist
            if inputs or outputs:
                ax.hist([inputs, outputs], label=['Input Tokens', 'Output Tokens'], color=['skyblue', 'salmon'])
                
            ax.set_title(f'Token Usage Histogram: {agent}')
            ax.set_xlabel('Tokens')
            ax.set_ylabel('Frequency')
            ax.legend()
            
            safe_agent_name = agent.replace(" ", "_").replace("/", "_").lower()
            plot_path = os.path.join(output_dir, f'token_usage_{safe_agent_name}.png')

            plt.tight_layout()
            plt.savefig(plot_path)
            plt.close()
            logger.info(f"Token usage histogram for {agent} saved to {plot_path}")

        # Save raw data text
        text_path = os.path.join(output_dir, 'token_usage_summary.txt')
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write("Token Usage Summary\n==================\n")
            for i, agent in enumerate(agents):
                f.write(f"\nAgent: {agent}\n")
                f.write(f"  Calls: {len(self.usage_records[agent])}\n")
                f.write(f"  Total Input: {total_inputs[i]}\n")
                f.write(f"  Total Output: {total_outputs[i]}\n")
                f.write(f"  Total Cached: {total_cached[i]}\n")
                f.write(f"  Cache Hit Rate: {total_cached[i] / max(total_inputs[i], 1) * 100:.1f}%\n")
                f.write(f"  Avg Input: {avg_inputs[i]:.2f}\n")
                f.write(f"  Avg Output: {avg_outputs[i]:.2f}\n")
