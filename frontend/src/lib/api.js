/**
 * ProofChain API client
 *
 * Thin wrapper around fetch() that handles:
 * - Base URL configuration
 * - JSON serialization
 * - Error handling
 */

const BASE_URL = import.meta.env.VITE_API_URL || ''

export async function verifyClaim(claim, maxIterations = 5) {
  const response = await fetch(`${BASE_URL}/api/v1/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claim, max_iterations: maxIterations }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export async function checkHealth() {
  const response = await fetch(`${BASE_URL}/health/live`)
  return response.ok
}