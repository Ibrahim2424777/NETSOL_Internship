// Centralized so a hook that invalidates a query always agrees with the
// hook that defined it - see useChats/useMessages/useSendMessage.
export const chatKeys = {
  all: ['chats'] as const,
  list: () => [...chatKeys.all, 'list'] as const,
  detail: (chatId: string) => [...chatKeys.all, 'detail', chatId] as const,
};

export const messageKeys = {
  all: ['messages'] as const,
  list: (chatId: string) => [...messageKeys.all, 'list', chatId] as const,
};
