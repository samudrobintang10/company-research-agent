import json
import logging
import os
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage
from openai import AsyncOpenAI
from backend.services.bjb_postgres_client import get_connection
from psycopg2.extras import RealDictCursor
from ..classes import ResearchState
from ..utils.references import format_references_section

logger = logging.getLogger(__name__)

class Editor:
    """Compiles individual section briefings into a cohesive final report."""

    def __init__(self) -> None:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        self.openai_client = AsyncOpenAI(api_key=self.openai_key)

        self.context = {
            "company": "Unknown Company",
            "industry": "Unknown",
            "hq_location": "Unknown"
        }

    async def compile_briefings(self, state: ResearchState) -> ResearchState:
        company = state.get('company', 'Unknown Company')
        self.context = {
            "company": company,
            "industry": state.get('industry', 'Unknown'),
            "hq_location": state.get('hq_location', 'Unknown')
        }

        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message=f"Starting report compilation for {company}",
                    result={"step": "Editor", "substep": "initialization"}
                )

        context = {
            "company": company,
            "industry": state.get('industry', 'Unknown'),
            "hq_location": state.get('hq_location', 'Unknown')
        }

        msg = [f"📑 Compiling final report for {company}..."]
        briefing_keys = {
            'company': 'company_briefing',
            'industry': 'industry_briefing',
            'financial': 'financial_briefing',
            'news': 'news_briefing'
        }

        if websocket_manager := state.get('websocket_manager'):
            if job_id := state.get('job_id'):
                await websocket_manager.send_status_update(
                    job_id=job_id,
                    status="processing",
                    message="Collecting section briefings",
                    result={"step": "Editor", "substep": "collecting_briefings"}
                )

        individual_briefings = {}
        for category, key in briefing_keys.items():
            if content := state.get(key):
                individual_briefings[category] = content
                msg.append(f"Found {category} briefing ({len(content)} characters)")
            else:
                msg.append(f"No {category} briefing available")
                logger.error(f"Missing state key: {key}")

        if not individual_briefings:
            msg.append("\n⚠️ No briefing sections available to compile")
            logger.error("No briefings found in state")
        else:
            try:
                compiled_report = await self.edit_report(state, individual_briefings, context)
                if not compiled_report:
                    logger.error("Compiled report is empty!")
                else:
                    logger.info(f"Successfully compiled report")
            except Exception as e:
                logger.error(f"Error during report compilation: {e}")
        state.setdefault('messages', []).append(AIMessage(content="\n".join(msg)))
        return state
    
    async def edit_report(self, state: ResearchState, briefings: Dict[str, str], context: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """Compile section briefings into a final report and update the state."""
        try:
            company = self.context["company"]
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Compiling initial research report",
                        result={"step": "Editor", "substep": "compilation"}
                    )

            edited_report = await self.compile_content(state, briefings, company)
            if not edited_report:
                logger.error("Initial compilation failed")
                return ""

            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Cleaning up and organizing report",
                        result={"step": "Editor", "substep": "cleanup"}
                    )

            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="processing",
                        message="Formatting final report",
                        result={"step": "Editor", "substep": "format"}
                    )

            final_report = await self.content_sweep(state, edited_report, company)
            final_report = final_report or ""

            logger.info(f"Final report compiled with {len(final_report)} characters")
            if not final_report.strip():
                logger.error("Final report is empty!")
                return ""

            logger.info("Final report preview:")
            logger.info(final_report[:500])

            state['report'] = final_report
            state['status'] = "editor_complete"

            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = final_report
            logger.info(f"Report length in state: {len(state.get('report', ''))}")

            product_recommendation = []
            try:
                with get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        cursor.execute("SELECT * FROM products WHERE deleted_at IS NULL")
                        all_products = cursor.fetchall()

                product_context = "\n".join([
                    f"- [ID: {p['id']}] {p['name']}\n  Deskripsi: {p.get('description', '-')}\n  Catatan: {p.get('note', '-')}\n  Prioritas: {p.get('priority', '-')}\n  Link: {p.get('link', '-')}\n"
                    for p in all_products
                ])
                recommendation_json_str = await self.generate_product_recommendation_json(context, final_report, product_context)
                product_recommendation = json.loads(recommendation_json_str)
                state['product_recommendation'] = product_recommendation
            except Exception as e:
                logger.error(f"Gagal memuat atau parse rekomendasi produk AI: {e}")
                state['product_recommendation'] = []
            
            if websocket_manager := state.get('websocket_manager'):
                if job_id := state.get('job_id'):
                    await websocket_manager.send_status_update(
                        job_id=job_id,
                        status="editor_complete",
                        message="Research report completed",
                        result={
                            "step": "Editor",
                            "report": final_report,
                            "company": company,
                            "is_final": True,
                            "status": "completed",
                            "product_recommendation": product_recommendation
                        }
                    )
            
            return final_report, product_recommendation
        except Exception as e:
            logger.error(f"Error in edit_report: {e}")
            return ""
        
    async def generate_product_recommendation_json(self, context: Dict[str, Any], final_report: str, product_context: str) -> str:
        prompt = f"""
Kamu adalah asisten cerdas dari Bank BJB. Berdasarkan profil perusahaan berikut ini, pilih produk yang relevan untuk ditawarkan.

## Profil Perusahaan:
Nama: {context['company']}
Industri: {context['industry']}
Lokasi Kantor Pusat: {context['hq_location']}

## Ringkasan Riset:
{final_report}

## Daftar Produk:
{product_context}

## Instruksi:
1. Jika perusahaan ini dinyatakan bangkrut, pailit, sedang dalam proses likuidasi, atau tidak beroperasi lagi, maka JANGAN rekomendasikan produk apapun. Langsung balas dengan array kosong: []
2. Jika perusahaan termasuk kategori UMKM atau bukan badan usaha (seperti individu, toko kecil, atau usaha rumahan), maka JANGAN tawarkan produk berikut:
   - Giro Korporasi
   - Deposito Korporasi
   - Payroll Service
   - Internet Banking Corporate
3. Jika perusahaan termasuk kategori perusahaan menengah atau besar, SELALU tawarkan keempat produk di atas tetapi jangan hanya itu saja, tawarkan yang lainnya juga (sebanyak-banyaknya) jika memang cocok.
4. Jika kamu memilih 'bjb Kredit Investasi', maka 'bjb Kredit Modal Kerja' juga HARUS disertakan (dan sebaliknya).
5. Pilih produk dari daftar yang relevan dan berikan rekomendasi dalam format JSON.
6. Gunakan struktur JSON seperti di bawah. **Isi `product_id` hanya dengan nilai ID numerik (angka integer) yang tersedia di daftar produk (yaitu `product.id`) — JANGAN MENGARANG.**
7. Struktur JSON:
[
  {{
    "product_id": 1,  // HARUS sama persis dengan ID produk di daftar
    "product_name": "Nama produk",
    "reason": "Jelaskan alasan produk ini cocok dan mengapa perusahaan ini penting bagi Bank BJB.",
    "potential": "Tuliskan potensi bisnis yang bisa didapatkan dari perusahaan ini",
    "reminder_notes": "Tambahkan catatan atau link terkait produk ini (jika ada) berdasarkan NOTES",
    "action": "Langkah yang perlu dilakukan tim Bank BJB terhadap perusahaan ini"
  }}
]
8. Hanya tampilkan produk yang benar-benar relevan.
9. Jangan tampilkan produk yang tidak relevan atau tidak ada di daftar produk.
10. Jangan menambahkan penjelasan lain di luar format JSON.
11. Balas hanya dalam format JSON. Tanpa markdown, tanpa komentar, dan tanpa teks di luar JSON.
"""

        response = await self.openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Kamu adalah AI assistant untuk bank yang bertugas menyarankan produk berdasarkan analisis riset perusahaan."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    
    async def compile_content(self, state: ResearchState, briefings: Dict[str, str], company: str) -> str:
        """Initial compilation of research sections."""
        combined_content = "\n\n".join(content for content in briefings.values())
        
        references = state.get('references', [])
        reference_text = ""
        if references:
            logger.info(f"Found {len(references)} references to add during compilation")
            
            # Get pre-processed reference info from curator
            reference_info = state.get('reference_info', {})
            reference_titles = state.get('reference_titles', {})
            
            logger.info(f"Reference info from state: {reference_info}")
            logger.info(f"Reference titles from state: {reference_titles}")
            
            # Use the references module to format the references section
            reference_text = format_references_section(references, reference_info, reference_titles)
            logger.info(f"Added {len(references)} references during compilation")
        
        # Use values from centralized context
        company = self.context["company"]
        industry = self.context["industry"]
        hq_location = self.context["hq_location"]
        
        prompt = f"""You are compiling a comprehensive research report about {company}.

Compiled briefings:
{combined_content}

Create a comprehensive and focused report on {company}, a {industry} company headquartered in {hq_location} that:
1. Integrates information from all sections into a cohesive non-repetitive narrative
2. Maintains important details from each section
3. Logically organizes information and removes transitional commentary / explanations
4. Uses clear section headers and structure

Formatting rules:
Strictly enforce this EXACT document structure:

# {company} Research Report

## Company Overview
[Company content with ### subsections]

## Industry Overview
[Industry content with ### subsections]

## Financial Overview
[Financial content with ### subsections]

## News
[News content with ### subsections]

Return the report using Bahasa Indonesia and in clean markdown format. No explanations or commentary."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert report editor that compiles research briefings into comprehensive company reports."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                stream=False
            )
            initial_report = response.choices[0].message.content.strip()
            
            # Append the references section after LLM processing
            if reference_text:
                initial_report = f"{initial_report}\n\n{reference_text}"
            
            return initial_report
        except Exception as e:
            logger.error(f"Error in initial compilation: {e}")
            return (combined_content or "").strip()
        
    async def content_sweep(self, state: ResearchState, content: str, company: str) -> str:
        """Sweep the content for any redundant information."""
        # Use values from centralized context
        company = self.context["company"]
        industry = self.context["industry"]
        hq_location = self.context["hq_location"]
        
        prompt = f"""You are an expert briefing editor. You are given a report on {company}.

Current report:
{content}

1. Remove redundant or repetitive information
2. Remove information that is not relevant to {company}, the {industry} company headquartered in {hq_location}.
3. Remove sections lacking substantial content
4. Remove any meta-commentary (e.g. "Here is the news...")

Strictly enforce this EXACT document structure:

## Company Overview
[Company content with ### subsections]

## Industry Overview
[Industry content with ### subsections]

## Financial Overview
[Financial content with ### subsections]

## News
[News content with ### subsections]

## References
[References in MLA format - PRESERVE EXACTLY AS PROVIDED]

Critical rules:
1. The document MUST start with "# {company} Research Report"
2. The document MUST ONLY use these exact ## headers in this order:
   - ## Company Overview
   - ## Industry Overview
   - ## Financial Overview
   - ## News
   - ## References
3. NO OTHER ## HEADERS ARE ALLOWED
4. Use ### for subsections in Company/Industry/Financial sections
5. News section should only use bullet points (*), never headers
6. Never use code blocks (```)
7. Never use more than one blank line between sections
8. Format all bullet points with *
9. Add one blank line before and after each section/list
10. DO NOT CHANGE the format of the references section

Return the polished report in flawless markdown format. No explanation.

Return the cleaned report in flawless markdown format. No explanations or commentary."""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4.1-mini", 
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert markdown formatter that ensures consistent document structure."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                stream=True
            )
            
            accumulated_text = ""
            buffer = ""
            
            async for chunk in response:
                if chunk.choices[0].finish_reason == "stop":
                    websocket_manager = state.get('websocket_manager')
                    if websocket_manager and buffer:
                        job_id = state.get('job_id')
                        if job_id:
                            await websocket_manager.send_status_update(
                                job_id=job_id,
                                status="report_chunk",
                                message="Formatting final report",
                                result={
                                    "chunk": buffer,
                                    "step": "Editor"
                                }
                            )
                    break
                    
                chunk_text = chunk.choices[0].delta.content
                if chunk_text:
                    accumulated_text += chunk_text
                    buffer += chunk_text
                    
                    if any(char in buffer for char in ['.', '!', '?', '\n']) and len(buffer) > 10:
                        if websocket_manager := state.get('websocket_manager'):
                            if job_id := state.get('job_id'):
                                await websocket_manager.send_status_update(
                                    job_id=job_id,
                                    status="report_chunk",
                                    message="Formatting final report",
                                    result={
                                        "chunk": buffer,
                                        "step": "Editor"
                                    }
                                )
                        buffer = ""
            
            return (accumulated_text or "").strip()
        except Exception as e:
            logger.error(f"Error in formatting: {e}")
            return (content or "").strip()

    async def run(self, state: ResearchState) -> ResearchState:
        state = await self.compile_briefings(state)
        # Ensure the Editor node's output is stored both top-level and under "editor"
        if 'report' in state:
            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = state['report']
        return state
