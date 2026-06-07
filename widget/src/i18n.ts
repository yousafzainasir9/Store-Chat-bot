// Minimal i18n: per-locale UI strings with a graceful fallback to English.
type Strings = Record<string, string>;

const EN: Strings = {
  launcher: "Chat with us",
  title: "Support",
  disclosure: "You're chatting with an AI assistant.",
  placeholder: "Type your message…",
  send: "Send",
  close: "Close chat",
  uploadImage: "Search by photo",
  typing: "Assistant is typing…",
  sources: "Sources",
  productsFound: "Products you might like:",
  errorGeneric: "Something went wrong. Please try again.",
  poweredBy: "AI assistant",
};

const LOCALES: Record<string, Strings> = {
  en: EN,
  es: {
    ...EN,
    launcher: "Chatea con nosotros",
    title: "Soporte",
    disclosure: "Estás chateando con un asistente de IA.",
    placeholder: "Escribe tu mensaje…",
    send: "Enviar",
    close: "Cerrar chat",
    uploadImage: "Buscar por foto",
    typing: "El asistente está escribiendo…",
    sources: "Fuentes",
    productsFound: "Productos que te pueden gustar:",
    errorGeneric: "Algo salió mal. Inténtalo de nuevo.",
  },
  fr: {
    ...EN,
    launcher: "Discutez avec nous",
    title: "Assistance",
    disclosure: "Vous discutez avec un assistant IA.",
    placeholder: "Écrivez votre message…",
    send: "Envoyer",
    close: "Fermer le chat",
    uploadImage: "Rechercher par photo",
    typing: "L'assistant écrit…",
    sources: "Sources",
    productsFound: "Produits qui pourraient vous plaire :",
    errorGeneric: "Une erreur s'est produite. Veuillez réessayer.",
  },
};

export function t(locale: string): (key: keyof typeof EN) => string {
  const dict = LOCALES[locale] ?? EN;
  return (key) => dict[key] ?? EN[key] ?? String(key);
}
