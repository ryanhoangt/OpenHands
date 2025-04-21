import { getBaseUrl } from "#/utils/api-helpers";

/**
 * Execute a bash command with streaming response
 * @param command The bash command to execute
 * @param onData Callback function that will be called with partial output data
 * @param onComplete Callback function that will be called when the command execution is complete
 * @param onError Callback function that will be called if an error occurs
 * @returns A function to abort the stream
 */
export function executeStreamingBashCommand(
  command: string,
  onData: (content: string, metadata: Record<string, unknown>) => void,
  onComplete?: () => void,
  onError?: (error: Error) => void
): () => void {
  const controller = new AbortController();
  const { signal } = controller;

  const baseUrl = getBaseUrl();
  const url = `${baseUrl}/execute_action_stream`;

  // Create the request payload
  const payload = {
    action: {
      action: "run",
      args: {
        command,
      },
    },
  };

  // Start the fetch request
  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      // Create a reader for the response body stream
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      // Function to read the stream
      function readStream(): Promise<void> {
        return reader.read().then(({ done, value }) => {
          if (done) {
            onComplete?.();
            return;
          }

          // Decode the chunk
          const chunk = decoder.decode(value, { stream: true });
          
          // Process the SSE data
          const lines = chunk.split("\n\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.substring(6));
                if (data.content !== undefined && data.metadata !== undefined) {
                  onData(data.content, data.metadata);
                }
              } catch (e) {
                console.error("Error parsing SSE data:", e);
              }
            }
          }

          // Continue reading
          return readStream();
        });
      }

      // Start reading the stream
      return readStream();
    })
    .catch((error) => {
      if (error.name !== "AbortError") {
        console.error("Error executing streaming bash command:", error);
        onError?.(error);
      }
    });

  // Return a function to abort the stream
  return () => controller.abort();
}