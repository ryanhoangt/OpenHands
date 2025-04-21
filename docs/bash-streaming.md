# Bash Command Streaming Support

This document describes the implementation of streaming support for bash command execution in OpenHands.

## Overview

The streaming functionality allows the frontend to receive partial results from long-running bash commands as they become available, rather than waiting for the entire command to complete. This provides a more responsive user experience, especially for commands that produce a lot of output or take a long time to complete.

## Backend Implementation

The backend implements a new endpoint `/execute_action_stream` that uses Server-Sent Events (SSE) to stream partial command outputs to the frontend. This endpoint is implemented in the runtime API.

## Frontend Implementation

The frontend implementation consists of several components:

### API Client

A new runtime API client is created in `frontend/src/api/runtime/runtime-api.ts` with a function `executeStreamingBashCommand` that connects to the streaming endpoint and processes the SSE events.

### Redux Store

The command slice in `frontend/src/state/command-slice.ts` is updated to handle partial command outputs with new actions:

- `startStreamingOutput`: Starts a new streaming command execution
- `updateStreamingOutput`: Updates the output of a streaming command with new content
- `completeStreamingOutput`: Marks a streaming command as complete

### Terminal Service

The terminal service in `frontend/src/services/terminal-service.ts` is updated with a new function `executeStreamingTerminalCommand` that uses the streaming endpoint to execute commands.

### Terminal Hook

The terminal hook in `frontend/src/hooks/use-terminal.ts` is updated to use the streaming command execution and handle the streaming state.

## Usage

The streaming functionality is enabled by default with a feature flag `USE_STREAMING` in the terminal hook. When enabled, all terminal commands will use the streaming endpoint instead of the WebSocket API.

## Abort Support

The implementation includes support for aborting streaming commands using Ctrl+C. When a user presses Ctrl+C while a command is streaming, the frontend will abort the streaming request and clean up the state.

## Testing

The implementation includes updates to the test files to support the new streaming functionality.