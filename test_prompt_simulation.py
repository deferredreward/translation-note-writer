#!/usr/bin/env python3
"""
Test Prompt Simulation Script
Simulates prompt assembly for specific support reference types without making AI calls.
"""

import os
import sys
from typing import Dict, Any, List

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_manager import ConfigManager
from modules.logger import setup_logging
from modules.sheet_manager import SheetManager
from modules.cache_manager import CacheManager
from modules.prompt_manager import PromptManager


def simulate_prompt_assembly():
    """Simulate prompt assembly for specific support reference types."""
    
    # Initialize components
    config = ConfigManager()
    logger = setup_logging(config)
    sheet_manager = SheetManager(config)
    cache_manager = CacheManager(config, sheet_manager)
    prompt_manager = PromptManager(config, cache_manager)
    
    logger.info("=== Translation Note Prompt Simulation ===")
    
    # Target support reference types
    target_types = [
        'writing-background',
        'figs-quotesinquotes', 
        'writing-newevent',
        'figs-imperative',
        'grammar-connect-logic-result'
    ]
    
    # Get cached data (templates, support references, system prompts)
    logger.info("Loading cached data...")
    templates = cache_manager.get_cached_data('templates')
    support_references = cache_manager.get_cached_data('support_references')
    system_prompts = cache_manager.get_cached_data('system_prompts')
    
    if not templates:
        logger.info("Fetching templates from Google Sheets...")
        templates = sheet_manager.fetch_templates()
        if templates:
            cache_manager.set_cached_data('templates', templates)
    
    if not support_references:
        logger.info("Fetching support references from Google Sheets...")
        support_references = sheet_manager.fetch_support_references()
        if support_references:
            cache_manager.set_cached_data('support_references', support_references)
    
    if not system_prompts:
        logger.info("Fetching system prompts from Google Sheets...")
        system_prompts = sheet_manager.fetch_system_prompts()
        if system_prompts:
            cache_manager.set_cached_data('system_prompts', system_prompts)
    
    # Simulate verse data (Genesis 1:10 as requested)
    simulated_verse_data = {
        'reference': 'GEN 1:10',
        'book': 'GEN',
        'chapter': 1,
        'verse': 10,
        'ult_text': 'God called the dry land "earth," and the gathering of the waters he called "seas." God saw that it was good.',
        'ust_text': 'God gave names to the dry land and to the water that was gathered together. He called the dry land "earth," and he called the gathered water "seas." God was pleased with what he saw.',
        'gl_quote': 'God called the dry land "earth"'
    }
    
    # Generate output content
    output_lines = []
    output_lines.append("=== TRANSLATION NOTE PROMPT SIMULATION ===")
    output_lines.append(f"Generated on: {logger.handlers[0].formatter.formatTime(logger.makeRecord('test', 20, '', 0, '', (), None))}")
    output_lines.append("")
    
    # Process each target support reference type
    for sref_type in target_types:
        output_lines.append(f"## Support Reference: {sref_type}")
        output_lines.append("=" * 50)
        
        # Find matching support reference
        matching_support_ref = None
        if support_references:
            for ref in support_references:
                if sref_type in ref.get('Issue', ''):
                    matching_support_ref = ref
                    break
        
        if matching_support_ref:
            output_lines.append(f"Support Reference Found: {matching_support_ref.get('Issue', 'N/A')}")
            output_lines.append(f"Type: {matching_support_ref.get('Type', 'N/A')}")
            output_lines.append(f"Description: {matching_support_ref.get('Description', 'N/A')}")
        else:
            output_lines.append(f"Support Reference: {sref_type} (not found in support references)")
        
        output_lines.append("")
        
        # Find matching template
        matching_template = None
        if templates:
            for template in templates:
                if sref_type in template.get('support reference', ''):
                    matching_template = template
                    break
        
        if matching_template:
            output_lines.append("Template Found:")
            for key, value in matching_template.items():
                if value and key not in ['row']:
                    output_lines.append(f"  {key}: {value}")
        else:
            output_lines.append(f"Template: Not found for {sref_type}")
        
        output_lines.append("")
        
        # Simulate template variables
        template_vars = {
            'reference': simulated_verse_data['reference'],
            'ult_text': simulated_verse_data['ult_text'],
            'ust_text': simulated_verse_data['ust_text'],
            'gl_quote': simulated_verse_data['gl_quote'],
            'sref': sref_type,
            'support_reference': matching_support_ref.get('Description', '') if matching_support_ref else '',
            'template_text': matching_template.get('note template', '') if matching_template else ''
        }
        
        # Generate system message
        system_message = prompt_manager.get_system_message('writes_at')
        if system_message:
            output_lines.append("SYSTEM MESSAGE:")
            output_lines.append(system_message)
        else:
            output_lines.append("SYSTEM MESSAGE: Not available")
        
        output_lines.append("")
        
        # Generate user prompt
        user_prompt = prompt_manager.get_prompt('writes_at', template_vars)
        output_lines.append("USER PROMPT:")
        output_lines.append(user_prompt)
        
        output_lines.append("")
        output_lines.append("VERSE CONTEXT:")
        output_lines.append(f"Reference: {simulated_verse_data['reference']}")
        output_lines.append(f"ULT: {simulated_verse_data['ult_text']}")
        output_lines.append(f"UST: {simulated_verse_data['ust_text']}")
        output_lines.append(f"GL Quote: {simulated_verse_data['gl_quote']}")
        
        output_lines.append("")
        output_lines.append("=" * 80)
        output_lines.append("")
    
    # Write output to file
    output_file = "prompt_simulation_output.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    logger.info(f"Prompt simulation complete. Output written to: {output_file}")
    
    # Show summary
    logger.info("\n=== SIMULATION SUMMARY ===")
    logger.info(f"Target support reference types: {len(target_types)}")
    logger.info(f"Templates loaded: {len(templates) if templates else 0}")
    logger.info(f"Support references loaded: {len(support_references) if support_references else 0}")
    logger.info(f"System prompts loaded: {len(system_prompts) if system_prompts else 0}")
    logger.info(f"Output file: {output_file}")


if __name__ == '__main__':
    simulate_prompt_assembly()