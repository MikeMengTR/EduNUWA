// Converts Windows absolute paths to fetchable /data/ URLs
export function resolveAudioPath(absolutePath: string): string {
  if (!absolutePath) return '';
  let normalized = absolutePath.replace(/\\/g, '/');
  const dataIndex = normalized.indexOf('data/');
  if (dataIndex !== -1) {
    return '/' + normalized.substring(dataIndex);
  }
  return normalized;
}
