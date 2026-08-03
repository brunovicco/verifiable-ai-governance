const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function isDemoReadOnly(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_READ_ONLY === "true";
}

export function isWriteMethod(method: string | undefined): boolean {
  return WRITE_METHODS.has((method ?? "GET").toUpperCase());
}

export function getDeploymentLabel(): string {
  return process.env.NEXT_PUBLIC_DEPLOYMENT_LABEL ?? "Ambiente local";
}

export function getGitSha(): string | undefined {
  return process.env.NEXT_PUBLIC_GIT_SHA || undefined;
}
