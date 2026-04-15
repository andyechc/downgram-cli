"""
Módulo de descarga de videos con gestión de carpetas y barra de progreso
"""

import os
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.console import Console
import re

console = Console()

class VideoDownloader:
    """Clase para manejar la descarga de videos con organización y progreso"""
    
    def __init__(self, downloads_folder: str = "downloads"):
        self.downloads_folder = Path(downloads_folder)
        self.downloaded_count = 0
        self.failed_count = 0
        
    def ensure_downloads_folder(self):
        """Asegura que la carpeta de descargas exista"""
        self.downloads_folder.mkdir(exist_ok=True)
        console.print(f"📁 Carpeta de descargas: {self.downloads_folder.absolute()}")
    
    def sanitize_filename(self, filename: str) -> str:
        """Limpia un nombre de archivo para que sea seguro para el sistema operativo"""
        # Eliminar caracteres no válidos
        invalid_chars = r'[<>:"/\\|?*]'
        filename = re.sub(invalid_chars, '_', filename)
        
        # Limitar longitud
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
        
        return filename
    
    def create_channel_folder(self, channel_name: str) -> Path:
        """Crea una carpeta para el canal si no existe"""
        safe_channel_name = self.sanitize_filename(channel_name)
        channel_folder = self.downloads_folder / safe_channel_name
        channel_folder.mkdir(exist_ok=True)
        return channel_folder
    
    async def download_media(self, telegram_manager, media_files: List[Dict[str, Any]], selected_indices: List[int]) -> Dict[str, int]:
        """Descarga los archivos de media seleccionados con barra de progreso"""
        selected_media = [media_files[i] for i in selected_indices]
        
        if not selected_media:
            return {'downloaded': 0, 'failed': 0}
        
        console.print(f"\n[bold blue]📥 Iniciando descarga de {len(selected_media)} archivos...[/bold blue]")
        
        # Reiniciar contadores
        self.downloaded_count = 0
        self.failed_count = 0
        
        with Progress(
            TextColumn("[bold blue]{task.description}", justify="right"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False  # Mantener la barra visible después de completar
        ) as progress:
            
            tasks = {}
            
            # Crear tareas para cada archivo de media
            for i, media in enumerate(selected_media):
                # Crear nombre de archivo
                channel_name = media['channel_title']
                filename = self._generate_filename(media)
                
                # Crear carpeta del canal
                channel_folder = self.create_channel_folder(channel_name)
                file_path = channel_folder / filename
                
                # Verificar si el archivo ya existe
                if file_path.exists():
                    console.print(f"[yellow]⚠️  El archivo ya existe: {filename}[/yellow]")
                    self.downloaded_count += 1
                    continue
                
                # Crear tarea de progreso
                file_size = media.get('file_size', 0)
                # Determinar icono según tipo de media
                media_type = media.get('media_type', 'video')
                if media_type == 'audio':
                    icon = "🎵"
                elif media_type == 'voice':
                    icon = "🎤"
                else:
                    icon = "📹"
                # Usar 0 como total inicial, se actualizará cuando el callback proporcione el tamaño real
                task_id = progress.add_task(
                    f"{icon} {filename[:50]}...",
                    total=0  # Total inicial, se actualizará dinámicamente
                )
                tasks[task_id] = {
                    'media': media,
                    'file_path': file_path,
                    'filename': filename,
                    'actual_size': 0  # Almacenará el tamaño real cuando se conozca
                }
            
            # Descargar archivos
            for task_id, media_info in tasks.items():
                await self._download_single_media(
                    telegram_manager,
                    progress,
                    task_id,
                    media_info['media'],
                    media_info['file_path'],
                    media_info['filename']
                )
        
        # Mostrar resumen
        self._show_download_summary(len(selected_media))
        
        return {
            'downloaded': self.downloaded_count,
            'failed': self.failed_count
        }
    
    async def _download_single_media(self, telegram_manager, progress, task_id: int, media: Dict[str, Any], file_path: Path, filename: str):
        """Descarga un archivo de media individual con actualización de progreso"""
        try:
            # Variable para almacenar el tamaño real
            actual_size = [0]  # Usar lista para poder modificar en el callback
            
            # Callback para actualizar progreso
            def progress_callback(current: int, total: int):
                # Si recibimos un tamaño total válido y aún no hemos establecido el total
                if total > 0 and progress.tasks[task_id].total == 0:
                    progress.update(task_id, total=total)
                    actual_size[0] = total
                
                # Actualizar progreso
                if total > 0:
                    progress.update(task_id, completed=current)
                elif current > 0 and actual_size[0] > 0:
                    progress.update(task_id, completed=min(current, actual_size[0]))
            
            # Descargar archivo usando el cliente de Telegram
            success = await telegram_manager.download_media(
                message=media['message_obj'],
                entity=media['entity'],
                file_path=str(file_path),
                progress_callback=progress_callback
            )
            
            if success:
                # Actualizar progreso al 100%
                if actual_size[0] > 0:
                    progress.update(task_id, completed=actual_size[0])
                else:
                    # Si nunca obtuvimos el tamaño real, actualizar con el progreso actual
                    current_progress = progress.tasks[task_id].completed
                    if current_progress > 0:
                        progress.update(task_id, total=current_progress, completed=current_progress)
                
                self.downloaded_count += 1
                console.print(f"[green]✅ Descargado: {filename}[/green]")
            else:
                self.failed_count += 1
                console.print(f"[red]❌ Error descargando: {filename}[/red]")
                progress.update(task_id, completed=0)
                
        except Exception as e:
            self.failed_count += 1
            console.print(f"[red]❌ Error descargando {filename}: {str(e)}[/red]")
            progress.update(task_id, completed=0)
    
    def _generate_filename(self, media: Dict[str, Any]) -> str:
        """Genera un nombre de archivo basado en la descripción del archivo de media"""
        # Obtener información básica
        media_id = media['id']
        message_text = media['message']
        media_type = media.get('media_type', 'video')
        mime_type = media.get('mime_type', '')
        
        # Determinar extensión según tipo de media
        if media_type == 'audio':
            # Intentar obtener extensión del MIME type para audio
            if mime_type:
                if 'mp3' in mime_type.lower():
                    extension = 'mp3'
                elif 'm4a' in mime_type.lower() or 'mp4' in mime_type.lower():
                    extension = 'm4a'
                elif 'ogg' in mime_type.lower():
                    extension = 'ogg'
                elif 'flac' in mime_type.lower():
                    extension = 'flac'
                elif 'wav' in mime_type.lower():
                    extension = 'wav'
                elif 'audio' in mime_type.lower():
                    extension = 'mp3'
                else:
                    extension = 'mp3'
            else:
                extension = 'mp3'
            default_name = "audio"
        elif media_type == 'voice':
            extension = 'ogg'
            default_name = "voice"
        else:  # video
            # Intentar obtener extensión del MIME type para video
            if mime_type:
                if 'mp4' in mime_type.lower():
                    extension = 'mp4'
                elif 'avi' in mime_type.lower():
                    extension = 'avi'
                elif 'mkv' in mime_type.lower():
                    extension = 'mkv'
                elif 'mov' in mime_type.lower():
                    extension = 'mov'
                elif 'webm' in mime_type.lower():
                    extension = 'webm'
                elif 'video' in mime_type.lower():
                    extension = 'mp4'
                else:
                    extension = 'mp4'
            else:
                extension = 'mp4'
            default_name = "video"
        
        # Sanitizar y usar la descripción como nombre principal
        safe_message = self.sanitize_filename(message_text) if message_text else ""
        
        # Si la descripción está vacía o es muy corta, usar el tipo + ID
        if len(safe_message.strip()) < 3:
            safe_message = f"{default_name}_{media_id}"
        
        # Limitar longitud para evitar nombres muy largos
        safe_message = safe_message[:80]
        
        # Generar nombre de archivo con la extensión correcta
        filename = f"{safe_message}.{extension}"
        
        return filename
    
    def _show_download_summary(self, total_files: int):
        """Muestra un resumen de la descarga"""
        console.print(f"\n[bold]📊 Resumen de Descarga[/bold]")
        console.print(f"Total de archivos: {total_files}")
        console.print(f"[green]✅ Descargados exitosamente: {self.downloaded_count}[/green]")
        
        if self.failed_count > 0:
            console.print(f"[red]❌ Fallidos: {self.failed_count}[/red]")
        
        success_rate = (self.downloaded_count / total_files * 100) if total_files > 0 else 0
        console.print(f"📈 Tasa de éxito: {success_rate:.1f}%")
        
        if self.downloaded_count > 0:
            console.print(f"\n📁 Los archivos se guardaron en: {self.downloads_folder.absolute()}")
    
    def get_downloaded_files_info(self) -> List[Dict[str, Any]]:
        """Obtiene información de los archivos descargados"""
        downloaded_files = []
        
        if not self.downloads_folder.exists():
            return downloaded_files
        
        for channel_folder in self.downloads_folder.iterdir():
            if channel_folder.is_dir():
                for media_file in channel_folder.iterdir():
                    if media_file.is_file() and media_file.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.m4a', '.ogg', '.flac', '.wav']:
                        stat = media_file.stat()
                        downloaded_files.append({
                            'filename': media_file.name,
                            'channel': channel_folder.name,
                            'size': stat.st_size,
                            'path': str(media_file),
                            'modified': stat.st_mtime
                        })
        
        return downloaded_files
