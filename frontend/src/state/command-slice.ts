import { createSlice } from "@reduxjs/toolkit";

export type Command = {
  content: string;
  type: "input" | "output";
  // For streaming output, we need to know if this is a partial output
  isPartial?: boolean;
  // Unique ID for the command to identify which command is being updated
  id?: string;
};

const initialCommands: Command[] = [];

export const commandSlice = createSlice({
  name: "command",
  initialState: {
    commands: initialCommands,
    // Track the current streaming command ID if any
    currentStreamingCommandId: null as string | null,
  },
  reducers: {
    appendInput: (state, action) => {
      state.commands.push({ content: action.payload, type: "input" });
    },
    appendOutput: (state, action) => {
      state.commands.push({ content: action.payload, type: "output" });
    },
    // Start a new streaming output
    startStreamingOutput: (state, action) => {
      const { content, id } = action.payload;
      state.currentStreamingCommandId = id;
      state.commands.push({ 
        content, 
        type: "output", 
        isPartial: true,
        id 
      });
    },
    // Update an existing streaming output
    updateStreamingOutput: (state, action) => {
      const { content, id } = action.payload;
      
      // Find the command with the matching ID
      const commandIndex = state.commands.findIndex(
        (cmd) => cmd.id === id
      );
      
      if (commandIndex !== -1) {
        // Update the content of the command
        state.commands[commandIndex].content += content;
      }
    },
    // Mark a streaming output as complete
    completeStreamingOutput: (state, action) => {
      const { id } = action.payload;
      
      // Find the command with the matching ID
      const commandIndex = state.commands.findIndex(
        (cmd) => cmd.id === id
      );
      
      if (commandIndex !== -1) {
        // Mark the command as no longer partial
        state.commands[commandIndex].isPartial = false;
      }
      
      // Clear the current streaming command ID
      state.currentStreamingCommandId = null;
    },
    clearTerminal: (state) => {
      state.commands = [];
      state.currentStreamingCommandId = null;
    },
  },
});

export const { 
  appendInput, 
  appendOutput, 
  startStreamingOutput,
  updateStreamingOutput,
  completeStreamingOutput,
  clearTerminal 
} = commandSlice.actions;

export default commandSlice.reducer;
