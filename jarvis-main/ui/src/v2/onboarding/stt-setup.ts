export type LocalSTTServerType = "whisper_cpp" | "openai_compatible";

export interface LocalSTTBlock {
  endpoint?: string;
  server_type?: LocalSTTServerType;
}

export interface LocalSTTForm {
  endpoint: string;
  serverType: LocalSTTServerType;
  /** The stored endpoint and dialect were read into the form. */
  loaded: boolean;
  /** Fields the user edited, so they hold a deliberate value. */
  touched: { endpoint: boolean; serverType: boolean };
}

/**
 * Build the `stt.local` block onboarding sends. The daemon deep-merges it into
 * the stored config, so an omitted field keeps its stored value.
 *
 * Once the stored values were loaded, the form shows what is saved and both
 * fields are sent. If that read failed, the form still holds defaults, and an
 * untouched default must not overwrite a dialect fixed earlier in Settings, so
 * only edited fields are sent. A blank endpoint is never sent. Returns
 * undefined when nothing should change.
 */
export function localSTTSetup(form: LocalSTTForm): LocalSTTBlock | undefined {
  const block: LocalSTTBlock = {};
  const endpoint = form.endpoint.trim();
  if (endpoint && (form.loaded || form.touched.endpoint)) block.endpoint = endpoint;
  if (form.loaded || form.touched.serverType) block.server_type = form.serverType;
  return block.endpoint === undefined && block.server_type === undefined ? undefined : block;
}
