import { useQuery } from '@tanstack/react-query';

import { listMessages } from '../services/messageApi';
import { messageKeys } from './queryKeys';

export function useMessages(chatId: string | undefined) {
  return useQuery({
    queryKey: messageKeys.list(chatId ?? ''),
    queryFn: () => listMessages(chatId as string),
    enabled: Boolean(chatId),
  });
}
