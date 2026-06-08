export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  text: string;
  citations?: string[];
  handoff?: boolean;
  pending?: boolean;
}

export interface ProductResult {
  product_id: string;
  title: string;
  price: number;
  url: string;
  reason: string;
}

export interface WidgetConfig {
  storeName: string;
  apiBase: string;
  primary: string;
  position: "left" | "right";
  locale: string;
  /** Optional opening assistant message (managed in the admin). */
  greeting?: string;
  /** Whether the image-upload (visual search) button is shown. */
  showImageUpload?: boolean;
}
