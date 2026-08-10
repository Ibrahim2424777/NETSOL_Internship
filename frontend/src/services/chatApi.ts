import apiClient from './apiClient';
import type { Chat } from '../types';

export async function listChats(): Promise<Chat[]> {
  const { data } = await apiClient.get<Chat[]>('/chats');
  return data;
}

export async function getChat(chatId: string): Promise<Chat> {
  const { data } = await apiClient.get<Chat>(`/chats/${chatId}`);
  return data;
}

export async function createChat(title?: string): Promise<Chat> {
  const { data } = await apiClient.post<Chat>('/chats', title ? { title } : {});
  return data;
}

export async function renameChat(chatId: string, title: string): Promise<Chat> {
  const { data } = await apiClient.patch<Chat>(`/chats/${chatId}`, { title });
  return data;
}

export async function deleteChat(chatId: string): Promise<void> {
  await apiClient.delete(`/chats/${chatId}`);
}
