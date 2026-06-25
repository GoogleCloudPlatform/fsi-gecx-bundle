"""
⚠️ WARNING: ADK LIBRARY MONKEYPATCH
This module monkeypatches the internal `GeminiLlmConnection.receive` method of the `google-adk` package.

PURPOSE:
By default, the ADK Gemini Live connection waits for a model turn completion before returning tool call
invocations. In voice-only sessions, this wait causes the agent to hang indefinitely when executing tools.
This patch intercepts incoming WebSocket events and yields tool calls immediately as they are received.

FRAGILITY NOTICE:
This patch utilizes name-mangled private methods of the ADK library (e.g. `_GeminiLlmConnection__build_full_text_response`).
Upgrading `google-adk` package versions may change these internal interfaces, causing imports or calls to fail.
Any package version updates should be accompanied by a validation check of this monkeypatch.
"""

import logging
from typing import AsyncGenerator
from google.adk.models.gemini_llm_connection import GeminiLlmConnection, LlmResponse
from google.genai import types
from google.adk.utils.context_utils import Aclosing
from google.adk.models.google_llm import GoogleLLMVariant

logger = logging.getLogger('patch_adk')

async def patched_receive(self) -> AsyncGenerator[LlmResponse, None]:
    """Receives the model response using the llm server connection, yielding tool calls immediately."""
    text = ''
    tool_call_parts = []
    
    async with Aclosing(self._gemini_session.receive()) as agen:
      async for message in agen:
        logger.debug('Got LLM Live message (patched): %s', message)
        live_session_id = self._gemini_session.session_id
        if message.usage_metadata:
          yield LlmResponse(
              usage_metadata=message.usage_metadata,
              model_version=self._model_version,
              live_session_id=live_session_id,
          )
        if message.server_content:
          content = message.server_content.model_turn

          if (
              not (content and content.parts)
              and message.server_content.grounding_metadata
              and not message.server_content.turn_complete
          ):
            yield LlmResponse(
                grounding_metadata=message.server_content.grounding_metadata,
                interrupted=message.server_content.interrupted,
                model_version=self._model_version,
                live_session_id=live_session_id,
            )

          if content and content.parts:
            llm_response = LlmResponse(
                content=content,
                interrupted=message.server_content.interrupted,
                model_version=self._model_version,
                live_session_id=live_session_id,
            )
            if not message.server_content.turn_complete:
              llm_response.grounding_metadata = (
                  message.server_content.grounding_metadata
              )
            if content.parts[0].text:
              text += content.parts[0].text
              llm_response.partial = True
            elif text and not content.parts[0].inline_data:
              yield self._GeminiLlmConnection__build_full_text_response(text)
              text = ''
            yield llm_response

          if message.server_content.input_transcription:
            if message.server_content.input_transcription.text:
              self._input_transcription_text += (
                  message.server_content.input_transcription.text
              )
              yield LlmResponse(
                  input_transcription=types.Transcription(
                      text=message.server_content.input_transcription.text,
                      finished=False,
                  ),
                  partial=True,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
            if message.server_content.input_transcription.finished:
              yield LlmResponse(
                  input_transcription=types.Transcription(
                      text=self._input_transcription_text,
                      finished=True,
                  ),
                  partial=False,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
              self._input_transcription_text = ''
          if message.server_content.output_transcription:
            if message.server_content.output_transcription.text:
              self._output_transcription_text += (
                  message.server_content.output_transcription.text
              )
              yield LlmResponse(
                  output_transcription=types.Transcription(
                      text=message.server_content.output_transcription.text,
                      finished=False,
                  ),
                  partial=True,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
            if message.server_content.output_transcription.finished:
              yield LlmResponse(
                  output_transcription=types.Transcription(
                      text=self._output_transcription_text,
                      finished=True,
                  ),
                  partial=False,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
              self._output_transcription_text = ''

          if self._api_backend == GoogleLLMVariant.GEMINI_API and (
              message.server_content.interrupted
              or message.server_content.turn_complete
              or message.server_content.generation_complete
          ):
            if self._input_transcription_text:
              yield LlmResponse(
                  input_transcription=types.Transcription(
                      text=self._input_transcription_text,
                      finished=True,
                  ),
                  partial=False,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
              self._input_transcription_text = ''
            if self._output_transcription_text:
              yield LlmResponse(
                  output_transcription=types.Transcription(
                      text=self._output_transcription_text,
                      finished=True,
                  ),
                  partial=False,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
              self._output_transcription_text = ''

          if message.server_content.turn_complete:
            if text:
              yield self._GeminiLlmConnection__build_full_text_response(text)
              text = ''
            if tool_call_parts:
              logger.debug('Returning aggregated tool_call_parts')
              yield LlmResponse(
                  content=types.Content(role='model', parts=tool_call_parts),
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
              tool_call_parts = []
            yield LlmResponse(
                turn_complete=True,
                interrupted=message.server_content.interrupted,
                grounding_metadata=message.server_content.grounding_metadata,
                model_version=self._model_version,
                live_session_id=live_session_id,
            )
            break

          if message.server_content.interrupted:
            if text:
              yield self._GeminiLlmConnection__build_full_text_response(text)
              text = ''
            else:
              yield LlmResponse(
                  interrupted=message.server_content.interrupted,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )

        if message.tool_call:
          logger.info('Received tool call: %s. Yielding immediately to runner (patched).', message.tool_call)
          if text:
            yield self._GeminiLlmConnection__build_full_text_response(text)
            text = ''
          
          # Yield immediately
          yield LlmResponse(
              content=types.Content(
                  role='model',
                  parts=[
                      types.Part(function_call=function_call)
                      for function_call in message.tool_call.function_calls
                  ]
              ),
              model_version=self._model_version,
              live_session_id=live_session_id,
          )

        if message.session_resumption_update:
          logger.debug('Received session resumption message: %s', message)
          yield (
              LlmResponse(
                  live_session_resumption_update=message.session_resumption_update,
                  model_version=self._model_version,
                  live_session_id=live_session_id,
              )
          )
        if message.go_away:
          logger.debug('Received GoAway message: %s', message.go_away)
          yield LlmResponse(
              go_away=message.go_away,
              model_version=self._model_version,
              live_session_id=live_session_id,
          )

      if tool_call_parts:
        logger.debug('Exited loop with pending tool_call_parts')
        yield LlmResponse(
            content=types.Content(role='model', parts=tool_call_parts),
            model_version=self._model_version,
            live_session_id=self._gemini_session.session_id,
        )

# Apply the patch
def apply_patch():
    logger.info("Applying ADK GeminiLlmConnection.receive monkeypatch...")
    GeminiLlmConnection.receive = patched_receive
