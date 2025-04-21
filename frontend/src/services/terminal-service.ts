import ActionType from "#/types/action-type";
import { executeStreamingBashCommand } from "#/api/runtime/runtime-api";
import { v4 as uuidv4 } from "uuid";
import { 
  startStreamingOutput, 
  updateStreamingOutput, 
  completeStreamingOutput 
} from "#/state/command-slice";
import { store } from "#/store";

/**
 * Create a terminal command event for WebSocket execution
 * @param command The command to execute
 * @param hidden Whether to hide the command output
 * @returns The command event
 */
export function getTerminalCommand(command: string, hidden: boolean = false) {
  const event = { action: ActionType.RUN, args: { command, hidden } };
  return event;
}

/**
 * Execute a terminal command with streaming output
 * @param command The command to execute
 * @returns A function to abort the stream
 */
export function executeStreamingTerminalCommand(command: string): () => void {
  // Generate a unique ID for this command execution
  const commandId = uuidv4();
  
  // Start the streaming output in the store
  store.dispatch(startStreamingOutput({ content: "", id: commandId }));
  
  // Execute the command with streaming
  return executeStreamingBashCommand(
    command,
    (content, metadata) => {
      // Update the streaming output in the store
      store.dispatch(updateStreamingOutput({ content, id: commandId }));
      
      // If this is the final output, mark it as complete
      if (metadata.is_complete) {
        store.dispatch(completeStreamingOutput({ id: commandId }));
      }
    },
    () => {
      // Command execution completed
      store.dispatch(completeStreamingOutput({ id: commandId }));
    },
    (error) => {
      // Handle error
      console.error("Error executing streaming command:", error);
      store.dispatch(completeStreamingOutput({ id: commandId }));
    }
  );
}
