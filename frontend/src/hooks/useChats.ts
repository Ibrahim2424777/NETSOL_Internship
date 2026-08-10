import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createChat, deleteChat, getChat, listChats, renameChat } from '../services/chatApi';
import { chatKeys, messageKeys } from './queryKeys';

export function useChats() {
  return useQuery({
    queryKey: chatKeys.list(),
    queryFn: listChats,
  });
}

export function useChat(chatId: string | undefined) {
  return useQuery({
    queryKey: chatKeys.detail(chatId ?? ''),
    queryFn: () => getChat(chatId as string),
    enabled: Boolean(chatId),
  });
}

export function useCreateChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => createChat(title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.list() });
    },
  });
}

export function useRenameChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chatId, title }: { chatId: string; title: string }) => renameChat(chatId, title),
    onSuccess: (updatedChat) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      queryClient.setQueryData(chatKeys.detail(updatedChat.id), updatedChat);
    },
  });
}

export function useDeleteChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chatId: string) => deleteChat(chatId),
    onSuccess: (_data, chatId) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      queryClient.removeQueries({ queryKey: chatKeys.detail(chatId) });
      queryClient.removeQueries({ queryKey: messageKeys.list(chatId) });
    },
  });
}
