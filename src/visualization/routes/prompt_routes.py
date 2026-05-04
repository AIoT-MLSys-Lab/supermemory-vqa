"""
Routes related to prompt discovery and rendering.
"""
import logging
import traceback
from flask import Blueprint, jsonify, request

from annotation.service import VideoAnnotationService
from utils.prompts import get_prompt_manager

logger = logging.getLogger(__name__)
prompt_bp = Blueprint('prompts', __name__)


@prompt_bp.route('/api/models')
def list_models():
    """List available Gemini models."""
    return jsonify(VideoAnnotationService.get_available_models())


@prompt_bp.route('/api/prompts')
def list_prompts():
    """List available annotation prompts."""
    try:
        prompt_manager = get_prompt_manager()
        return jsonify(prompt_manager.list_prompts())
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error listing prompts: %s", exc)
        return jsonify({'error': 'Failed to load prompts'}), 500


@prompt_bp.route('/api/prompts/<prompt_id>')
def get_prompt_details(prompt_id):
    """Get detailed information about a specific prompt including parameters."""
    try:
        prompt_manager = get_prompt_manager()
        prompt = prompt_manager.get_prompt(prompt_id)

        return jsonify({
            'id': prompt.id,
            'name': prompt.name,
            'description': prompt.description,
            'version': prompt.version,
            'input_parameters': prompt.input_parameters,
            'is_dataclass': prompt.is_dataclass
        })
    except KeyError:
        return jsonify({'error': f'Prompt not found: {prompt_id}'}), 404
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error getting prompt details: %s", exc)
        return jsonify({'error': 'Failed to get prompt details'}), 500


@prompt_bp.route('/api/prompts/<prompt_id>/build', methods=['POST'])
def build_prompt(prompt_id):
    """Build/preview the rendered prompt with given parameters."""
    try:
        prompt_manager = get_prompt_manager()
        prompt = prompt_manager.get_prompt(prompt_id)

        data = request.get_json() or {}
        parameters = data.get('parameters', {})

        rendered_prompt = prompt.render(**parameters)

        return jsonify({
            'success': True,
            'prompt_id': prompt_id,
            'parameters': parameters,
            'rendered_prompt': rendered_prompt
        })
    except KeyError:
        return jsonify({'error': f'Prompt not found: {prompt_id}'}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error building prompt: %s\n%s", exc, traceback.format_exc())
        return jsonify({'error': 'Failed to build prompt'}), 500
