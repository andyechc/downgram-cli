#!/usr/bin/env python3
"""
Downgram CLI - Script Principal
Una herramienta CLI interactiva para filtrar y descargar videos de Telegram
"""

import asyncio
import sys
import signal
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.prompt import Prompt

# Importar módulos personalizados
from config import Config
from telegram_client import TelegramManager
from ui import UserInterface
from downloader import VideoDownloader

console = Console()

class DowngramCLI:
    """Clase principal que coordina toda la aplicación"""
    
    def __init__(self):
        self.config = Config()
        self.telegram_manager: Optional[TelegramManager] = None
        self.ui = UserInterface()
        self.downloader = VideoDownloader(self.config.downloads_folder)
        self.is_running = False
    
    def setup_signal_handlers(self):
        """Configura manejadores de señales para cierre elegante"""
        def signal_handler(signum, frame):
            print("\n🛑 Cerrando aplicación...")
            self.is_running = False
            if self.telegram_manager:
                asyncio.create_task(self.telegram_manager.disconnect())
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run(self):
        """Ejecuta la aplicación principal"""
        self.is_running = True
        self.setup_signal_handlers()
        
        try:
            # 1. Mostrar bienvenida
            self.ui.show_welcome()
            
            # 2. Validar configuración
            if not self.config.validate_credentials():
                self.ui.show_error("Credenciales inválidas. Verifica tu archivo .env")
                return
            
            # 3. Crear carpeta de descargas
            self.downloader.ensure_downloads_folder()
            
            # 4. Conectar a Telegram
            if not await self._connect_to_telegram():
                return
            
            # 5. Ejecutar flujo principal
            await self._run_main_flow()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️  Aplicación interrumpida por el usuario[/yellow]")
        except Exception as e:
            self.ui.show_error(f"Error inesperado: {str(e)}", "Error Crítico")
        finally:
            # 6. Desconectar de Telegram
            await self._cleanup()
    
    async def _connect_to_telegram(self) -> bool:
        """Establece conexión con Telegram"""
        try:
            api_id, api_hash, phone = self.config.get_api_credentials()
            self.telegram_manager = TelegramManager(api_id, api_hash, phone, self.config.session_name)
            
            connected = await self.telegram_manager.connect()
            
            if not connected:
                self.ui.show_error("No se pudo conectar a Telegram. Verifica tus credenciales.")
                return False
            
            return True
            
        except ValueError as e:
            self.ui.show_error(str(e))
            return False
        except Exception as e:
            self.ui.show_error(f"Error de conexión: {str(e)}")
            return False
    
    async def _run_main_flow(self):
        """Ejecuta el flujo principal de la aplicación con navegación entre pasos"""
        # Estado del flujo: 'menu' -> 'channels' -> 'keyword' -> 'search' -> 'download'
        current_state = 'menu'
        
        # Variables para mantener estado entre navegaciones
        dialogs = None
        selected_entities = None
        selected_channel_names = None
        keyword = None
        all_selected_media = []
        
        while self.is_running:
            try:
                # ========== MENÚ PRINCIPAL ==========
                if current_state == 'menu':
                    # Obtener y mostrar canales
                    dialogs = await self.telegram_manager.get_recent_dialogs(limit=50)
                    
                    if not dialogs:
                        self.ui.show_error("No se encontraron canales o grupos disponibles")
                        # En caso de error, preguntar si quiere salir o reintentar
                        if not self.ui.confirm_action("¿Deseas intentar nuevamente?"):
                            break
                        continue
                    
                    current_state = 'channels'
                    continue
                
                # ========== SELECCIÓN DE CANALES ==========
                if current_state == 'channels':
                    selected_channel_indices, action = self.ui.show_channels_table(dialogs)
                    
                    if action == 'exit':
                        # Salir de la aplicación solo si se escribe 'exit'
                        break
                    
                    if action == 'back':
                        # Volver al menú principal (recargar canales)
                        current_state = 'menu'
                        continue
                    
                    if not selected_channel_indices:
                        # Si no seleccionó nada, volver a mostrar canales
                        continue
                    
                    # Guardar selección
                    selected_entities = [dialogs[i]['entity'] for i in selected_channel_indices]
                    selected_channel_names = [dialogs[i]['title'] for i in selected_channel_indices]
                    
                    console.print(f"[green]✅ Canales seleccionados: {len(selected_entities)}[/green]")
                    for name in selected_channel_names:
                        console.print(f"  📺 {name}")
                    
                    current_state = 'keyword'
                    continue
                
                # ========== BÚSQUEDA DE MEDIA ==========
                if current_state == 'keyword':
                    keyword, action = self.ui.get_search_keyword()
                    
                    if action == 'back':
                        # Volver a selección de canales
                        current_state = 'channels'
                        continue
                    
                    # Reiniciar lista de archivos seleccionados
                    all_selected_media = []
                    current_state = 'search'
                    continue
                
                # ========== RESULTADOS DE BÚSQUEDA ==========
                if current_state == 'search':
                    search_success = await self._handle_search_and_selection(
                        selected_entities, keyword, all_selected_media
                    )
                    
                    if search_success == 'back':
                        # Volver a la búsqueda (cambiar palabra clave)
                        current_state = 'keyword'
                        continue
                    
                    if search_success == 'menu':
                        # Volver al menú principal
                        current_state = 'menu'
                        continue
                    
                    if not all_selected_media:
                        # No seleccionó archivos, preguntar qué hacer
                        if not self.ui.confirm_action("¿Deseas realizar otra búsqueda?"):
                            # Volver al menú principal
                            current_state = 'menu'
                        else:
                            # Volver a la búsqueda con misma palabra clave
                            all_selected_media = []
                        continue
                    
                    current_state = 'download'
                    continue
                
                # ========== DESCARGA ==========
                if current_state == 'download':
                    # Preguntar por la carpeta de descarga antes de comenzar
                    default_folder = str(self.downloader.downloads_folder)
                    custom_folder = self.ui.select_download_folder(default_folder)
                    
                    if custom_folder:
                        self.downloader.set_custom_download_folder(custom_folder)
                    else:
                        self.downloader.reset_to_default_folder()
                    
                    # Asegurar que la carpeta exista
                    self.downloader.ensure_downloads_folder()
                    
                    download_results = await self.downloader.download_media(
                        self.telegram_manager,
                        all_selected_media,
                        list(range(len(all_selected_media)))
                    )
                    
                    # Mostrar resumen final
                    self.ui.show_completion_message(
                        download_results['downloaded'],
                        len(all_selected_media)
                    )
                    
                    # Preguntar qué hacer después de descargar
                    console.print("\n[bold]¿Qué deseas hacer?[/bold]")
                    console.print("[dim]  • 'menu' - Volver al menú principal[/dim]")
                    console.print("[dim]  • 'search' - Realizar otra búsqueda (mismos canales)[/dim]")
                    console.print("[dim]  • 'exit' - Salir de la aplicación[/dim]")
                    
                    next_action = Prompt.ask(
                        "Selecciona opción",
                        default="menu"
                    ).lower().strip()
                    
                    if next_action == 'exit':
                        break
                    elif next_action == 'search':
                        all_selected_media = []
                        current_state = 'keyword'
                    else:
                        # Volver al menú principal
                        all_selected_media = []
                        selected_entities = None
                        selected_channel_names = None
                        keyword = None
                        current_state = 'menu'
                    
                    continue
                    
            except Exception as e:
                self.ui.show_error(f"Error en el flujo principal: {str(e)}")
                if not self.ui.confirm_action("¿Deseas intentar nuevamente?"):
                    break
    
    async def _handle_search_and_selection(self, selected_entities, keyword, all_selected_media):
        """Maneja la búsqueda y selección de media con paginación. Retorna 'back', 'menu', o True."""
        current_page = 0
        
        while True:
            # Realizar búsqueda para la página actual
            search_result = await self.telegram_manager.search_media(
                entities=selected_entities,
                keyword=keyword,
                limit=self.config.max_search_results,
                offset=current_page
            )
            
            # Mostrar resultados y selección
            selected_media_indices, navigation_action = self.ui.show_search_results(search_result)
            
            # Manejar opción de volver atrás
            if navigation_action == 'back':
                return 'back'
            
            # Manejar navegación de páginas
            if navigation_action == 'next':
                current_page += 1
                continue
            elif navigation_action == 'prev':
                current_page = max(0, current_page - 1)
                continue
            elif navigation_action and navigation_action.startswith('page_'):
                target_page = int(navigation_action.split('_')[1]) - 1
                current_page = target_page
                continue
            
            # Si hay media seleccionado, agregarlo a la lista
            if selected_media_indices:
                page_media = search_result['media']
                for idx in selected_media_indices:
                    all_selected_media.append(page_media[idx])
                
                # Preguntar si desea seleccionar más media de otras páginas
                if search_result['total_pages'] > 1:
                    if self.ui.confirm_action("¿Deseas seleccionar archivos de otras páginas?"):
                        # Permitir navegar a otras páginas
                        nav_choice = Prompt.ask(
                            "📍 Navegar a: [next/prev/page N/finish/back]",
                            default="finish"
                        ).lower().strip()
                        
                        if nav_choice == 'back':
                            # Volver a la búsqueda (sin guardar selección actual)
                            all_selected_media.clear()
                            return 'back'
                        elif nav_choice == 'next' and current_page < search_result['total_pages'] - 1:
                            current_page += 1
                            continue
                        elif nav_choice == 'prev' and current_page > 0:
                            current_page -= 1
                            continue
                        elif nav_choice.startswith('page '):
                            try:
                                page_num = int(nav_choice.split(' ')[1]) - 1
                                if 0 <= page_num < search_result['total_pages']:
                                    current_page = page_num
                                    continue
                            except (ValueError, IndexError):
                                console.print("[red]❌ Página inválida[/red]")
                        # Si no quiere navegar más, salir del bucle
            
            # Salir del bucle de paginación
            return True
    
    async def _cleanup(self):
        """Limpieza y cierre de recursos"""
        if self.telegram_manager:
            await self.telegram_manager.disconnect()
        
        console.print("\n[bold green]👋 ¡Hasta luego![/bold green]")

def main():
    """Función principal de entrada"""
    try:
        # Verificar versión de Python
        if sys.version_info < (3, 7):
            print("❌ Esta aplicación requiere Python 3.7 o superior")
            sys.exit(1)
        
        # Crear y ejecutar la aplicación
        app = DowngramCLI()
        asyncio.run(app.run())
        
    except KeyboardInterrupt:
        print("\n👋 ¡Hasta luego!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
