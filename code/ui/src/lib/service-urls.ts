declare global {
  interface Window {
    // Written at container start by infrastructure/docker/ui/40-app-config.sh.
    __APP_CONFIG__?: { airflowUrl?: string; flinkUrl?: string; apiMode?: string }
  }
}

const config = window.__APP_CONFIG__ ?? {}

/** Builds the URL of another service on the same host, including GitHub Codespaces port forwarding. */
function sameHost(port: number) {
  const { protocol, hostname } = window.location
  const codespace = hostname.match(/^(.*)-\d+(\.app\.github\.dev)$/)
  if (codespace) return `${protocol}//${codespace[1]}-${port}${codespace[2]}`
  return `${protocol}//${hostname}:${port}`
}

export const serviceUrls = {
  airflow: config.airflowUrl || sameHost(8080),
  flink: config.flinkUrl || sameHost(8081),
}

export const airflowDagUrl = (dagId: string) => `${serviceUrls.airflow}/dags/${dagId}`
