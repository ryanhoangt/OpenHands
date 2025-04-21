/**
 * Get the base URL for API requests
 * @returns The base URL for API requests
 */
export function getBaseUrl(): string {
  // Use the environment variable if available, otherwise use the current host
  const baseUrl = import.meta.env.VITE_BACKEND_BASE_URL || window?.location.origin;
  return baseUrl;
}