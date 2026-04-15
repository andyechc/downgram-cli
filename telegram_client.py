"""
Módulo de conexión a Telegram usando Telethon
Maneja la conexión, autenticación y operaciones básicas
"""

import asyncio
from typing import List, Dict, Any, Optional
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import InputPeerChannel, InputPeerChat
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

class TelegramManager:
    """Clase para manejar la conexión y operaciones con Telegram"""
    
    def __init__(self, api_id: int, api_hash: str, phone: str, session_name: str = "telegram_session"):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_name = session_name
        self.client: Optional[TelegramClient] = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Establece conexión con Telegram"""
        try:
            console.print("[bold blue]🔐 Conectando a Telegram...[/bold blue]")
            
            # Crear cliente con sesión persistente
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            
            # Iniciar conexión
            await self.client.start(phone=self.phone)
            self.is_connected = True
            
            # Verificar si estamos autenticados
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                console.print(Panel(
                    f"[green]✅ Conexión exitosa[/green]\n"
                    f"Usuario: {me.first_name} {me.last_name or ''}\n"
                    f"ID: {me.id}",
                    title="Telegram Conectado",
                    border_style="green"
                ))
                return True
            else:
                console.print("[red]❌ Error de autenticación[/red]")
                return False
                
        except FloodWaitError as e:
            console.print(f"[red]⏰ Límite de Telegram: espera {e.seconds} segundos[/red]")
            return False
        except RPCError as e:
            console.print(f"[red]❌ Error de RPC: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Error de conexión: {e}[/red]")
            return False
    
    async def get_recent_dialogs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene los diálogos recientes (canales, grupos y bots)"""
        if not self.is_connected or not self.client:
            raise RuntimeError("No hay conexión activa con Telegram")
        
        try:
            dialogs = []
            async for dialog in self.client.iter_dialogs(limit=limit):
                entity = dialog.entity
                
                # Filtrar canales, grupos y chats con bots
                is_bot_chat = False
                if dialog.is_user and hasattr(entity, 'bot') and entity.bot:
                    is_bot_chat = True
                
                if dialog.is_channel or dialog.is_group or is_bot_chat:
                    # Obtener información adicional
                    participants_count = getattr(entity, 'participants_count', 'N/A')
                    
                    # Determinar el tipo
                    if is_bot_chat:
                        dialog_type = 'Bot'
                    elif dialog.is_channel:
                        dialog_type = 'Canal'
                    else:
                        dialog_type = 'Grupo'
                    
                    dialogs.append({
                        'id': dialog.id,
                        'title': dialog.title or getattr(entity, 'first_name', 'Sin nombre'),
                        'type': dialog_type,
                        'participants': participants_count,
                        'entity': entity
                    })
            
            return dialogs
            
        except FloodWaitError as e:
            console.print(f"[red]⏰ Límite de Telegram: espera {e.seconds} segundos[/red]")
            return []
        except Exception as e:
            console.print(f"[red]❌ Error obteniendo diálogos: {e}[/red]")
            return []
    
    async def search_media(self, entities: List[Any], keyword: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """Busca videos y audios en las entidades especificadas con paginación"""
        if not self.is_connected or not self.client:
            raise RuntimeError("No hay conexión activa con Telegram")
        
        media_files = []
        total_found = 0
        skipped_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"🔍 Buscando media con '{keyword}'...", total=len(entities))
            
            for entity in entities:
                try:
                    # Buscar mensajes en la entidad sin límite para buscar todo el historial
                    entity_media = []
                    async for message in self.client.iter_messages(
                        entity=entity,
                        search=keyword,
                        limit=None,  # Sin límite para buscar todo el historial
                        filter=None
                    ):
                        media_info = None
                        media_type = None
                        
                        # Verificar si el mensaje contiene video
                        if message.video and message.media:
                            media_info = message.video
                            media_type = 'video'
                        # Verificar si el mensaje contiene audio
                        elif message.audio and message.media:
                            media_info = message.audio
                            media_type = 'audio'
                        # Verificar si es mensaje de voz
                        elif message.voice and message.media:
                            media_info = message.voice
                            media_type = 'voice'
                        
                        if media_info and media_type:
                            # Extraer atributos del media con más métodos
                            duration = getattr(media_info, 'duration', 0)
                            file_size = getattr(media_info, 'file_size', 0)
                            width = getattr(media_info, 'width', 0)
                            height = getattr(media_info, 'height', 0)
                            mime_type = getattr(media_info, 'mime_type', '')
                            
                            # Intentar obtener tamaño de otras formas
                            if file_size == 0 and hasattr(media_info, 'size'):
                                file_size = getattr(media_info, 'size', 0)
                            
                            # Criterios para considerar un archivo válido
                            is_valid_media = False
                            if media_type == 'video':
                                is_valid_media = (
                                    (duration > 0) or
                                    (file_size > 0) or
                                    (width > 0 and height > 0) or
                                    (mime_type and 'video' in mime_type.lower())
                                )
                            elif media_type in ('audio', 'voice'):
                                is_valid_media = (
                                    (duration > 0) or
                                    (file_size > 0) or
                                    (mime_type and ('audio' in mime_type.lower() or 'ogg' in mime_type.lower()))
                                )
                            
                            if is_valid_media:
                                media_data = {
                                    'id': message.id,
                                    'date': message.date.strftime('%Y-%m-%d %H:%M'),
                                    'channel_title': getattr(entity, 'title', getattr(entity, 'first_name', 'Desconocido')),
                                    'message': message.message or 'Sin descripción',
                                    'duration': duration,
                                    'file_size': file_size,
                                    'width': width,
                                    'height': height,
                                    'mime_type': mime_type,
                                    'media_type': media_type,
                                    'message_obj': message,
                                    'entity': entity
                                }
                                entity_media.append(media_data)
                            else:
                                skipped_count += 1
                    
                    total_found += len(entity_media)
                    media_files.extend(entity_media)
                    
                    # Mostrar información de depuración
                    if skipped_count > 0:
                        console.print(f"[dim]ℹ️  {getattr(entity, 'title', getattr(entity, 'first_name', 'entidad'))}: {len(entity_media)} archivos válidos, {skipped_count} omitidos[/dim]")
                
                except FloodWaitError as e:
                    console.print(f"[yellow]⏰ Esperando {e.seconds} segundos por límite de API...[/yellow]")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    console.print(f"[red]❌ Error buscando en {getattr(entity, 'title', 'entidad')}: {e}[/red]")
                
                progress.advance(task)
        
        # Ordenar resultados por fecha (más recientes primero)
        media_files.sort(key=lambda x: x['date'], reverse=True)
        
        # Aplicar paginación
        page_size = 50
        start_idx = offset * page_size
        end_idx = start_idx + page_size
        
        paginated_media = media_files[start_idx:end_idx]
        has_more = end_idx < len(media_files)
        
        # Mostrar resumen de búsqueda
        if skipped_count > 0:
            console.print(f"[yellow]ℹ️  Se omitieron {skipped_count} mensajes sin media válido[/yellow]")
        
        return {
            'media': paginated_media,
            'total_found': len(media_files),
            'current_page': offset + 1,
            'total_pages': (len(media_files) + page_size - 1) // page_size,
            'has_more': has_more,
            'page_size': page_size
        }
    
    async def download_media(self, message: Any, entity: Any, file_path: str, progress_callback=None) -> bool:
        """Descarga un archivo de media específico (video, audio, etc.)"""
        if not self.is_connected or not self.client:
            raise RuntimeError("No hay conexión activa con Telegram")
        
        try:
            # Descargar el archivo con progreso
            await self.client.download_media(
                message=message,
                file=file_path,
                progress_callback=progress_callback
            )
            return True
            
        except FloodWaitError as e:
            console.print(f"[red]⏰ Límite de descarga: espera {e.seconds} segundos[/red]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Error descargando archivo: {e}[/red]")
            return False
    
    async def disconnect(self):
        """Cierra la conexión con Telegram"""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            console.print("[yellow]🔌 Conexión cerrada[/yellow]")
