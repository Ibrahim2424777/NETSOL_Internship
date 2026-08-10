import apiClient from './apiClient';
import type { Message } from '../types';

export async function listMessages(chatId: string): Promise<Message[]> {
  const { data } = await apiClient.get<Message[]>(`/chats/${chatId}/messages`);
  return data;
}
