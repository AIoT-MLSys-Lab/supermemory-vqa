<div align="center">

# 🧠 SuperMemory-VQA: An Egocentric Visual Question Answering Benchmark for Long-Horizon Memory

**Official repository for SuperMemory-VQA.** *Paper currently under review at NeurIPS 2026 (Datasets and Benchmarks Track)*

<br>

[![Repository License](https://img.shields.io/badge/Repository_License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Paper](https://img.shields.io/badge/NeurIPS_2026-Under_Review-4B5563.svg?style=flat-square)](supermemory_neurips/neurips_2026.pdf)
[![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97_Hugging_Face-Datasets-F9A825.svg?style=flat-square)](https://huggingface.co/datasets/OSU-AIoT-MLSys-Lab/SuperMemory-VQA)
[![GitHub](https://img.shields.io/badge/GitHub-Code-24292E.svg?style=flat-square&logo=github)](https://github.com/AIoT-MLSys-Lab/supermemory-vqa)

---

</div>

---

<div align="center">

| 📹 **52.9 Hours of Video** | 🧩 **4,853 Grounded Q&As** | 🛡️ **Hallucination Robust** | 🕶️ **Rich Sensor Modalities** |
| :---: | :---: | :---: | :---: |
| Everyday activities recorded via Gen 1 Meta Aria Glasses | Human-in-the-loop verified episodic, conversational, and procedural QA | Multiple-choice including ordered vague & "unanswerable" options | Synchronized RGB, audio transcript, eye gaze, IMU, and SLAM |

</div>

---

## 🌟 Overview

As AI agents integrate into Augmented Reality (AR) glasses, they have the potential to act as personalized memory assistants—helping users locate misplaced objects, recall spoken details, and reconstruct daily timelines. However, existing datasets predominantly focus on short-term perception or action recognition.

**SuperMemory-VQA** is a multi-modal egocentric Visual Question Answering (VQA) benchmark designed around questions people *actually* ask memory assistants. Built with continuous recordings spanning hours (and up to two weeks), it challenges model capability across five key dimensions:

1. **Natural Conversational Phrasing:** Context-dependent queries instead of predictable templates.
2. **Long-Horizon Context:** Multi-hour recordings that test the boundaries of context scaling.
3. **Dense Multi-Evidence Retrieval:** Questions requiring linking disjoint moments across vast temporal gaps (e.g., matching a spoken plan to later visual results).
4. **Grounded Multi-Modal Reasoning:** Seamlessly aligning video, audio transcript, gaze tracking, motion, and spatial context.
5. **Epistemic Calibration & Abstention:** Each multiple-choice question contains ordered answer options (**Correct > Vague > Wrong > Unanswerable**) to test whether models know when they have sufficient evidence or if they hallucinate.

---

## 📂 Dataset Tasks

SuperMemory-VQA evaluates agents across **six user-validated memory categories** reflecting actual human memory needs:

*   📍 **Object & Location Memory:** Recalling the last known position of an object, its state modifications, and its spatial trajectory over time.
*   💬 **Conversational Memory:** Retrieving spoken commitments, instruction corrections, deferred answers, and dialogue states from audio transcripts.
*   👁️ **Visual Scene Recall:** Retrieving specific fine-grained visual details (e.g., text on screens, manual ingredients, visible landmarks).
*   🔗 **In-Context Retrieval:** Synthesizing current visual cues with prior facts and associations to navigate complex relational memory tasks.
*   ⏱️ **Timeline Reconstruction:** Chronologically sequencing disjoint events to evaluate temporal and procedural episodic memory.
*   🎯 **Intent Recall:** Recovering stated or implied future goals, reminders, and prospective action intentions.

---

## 📊 Comparison with Existing Benchmarks

Unlike typical egocentric benchmarks that focus on short clips or simple action labels, **SuperMemory-VQA** provides a comprehensive environment for long-context multi-evidence retrieval.

| Dataset | Focus | Hrs | Context | QAs | Multi-Evid. | Natural Queries | Evaluation Type |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **EPIC-KITCHENS-100** | Action Rec. | 100 | ≈ 8.5m | -- | -- | No | Verb-noun labels & narrations |
| **Ego4D** | Ego Activities | 3,670 | ≈ 23m | -- | -- | No | Temporal/spatial localization |
| **EgoSchema** | Long Video QA | > 250 | 3m | 5,063 | Single | No | 5-way MCQ over localized clips |
| **EgoLife** | Life Assistant | 300 | > 1h | 6,000 | Limited | No | Generic MCQ with evidence timestamps |
| **SuperMemory-VQA (Ours)** | **SuperMemory** | **52.9** | **> 1h** | **4,853** | **34%** | **Yes** | **Ordered MCQs with time spans** |

---

## ⚙️ Setup and Installation

### 1. Prerequisites
Ensure you have **Python 3.10+** and **Node.js** (for building the Svelte frontend UI) installed.

### 2. Clone and Install Dependencies
```bash
git clone https://github.com/AIoT-MLSys-Lab/supermemory-vqa.git
cd supermemory-vqa
```

Create a virtual environment and install Python requirements:
```bash
python -m venv venv
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Copy the template `.env.example` to create your own configuration file:
```bash
# On Windows:
copy .env.example .env
# On macOS/Linux:
cp .env.example .env
```
Open `.env` and set your **Gemini API Key**:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

---

## 🚀 Running the Annotation Pipeline

SuperMemory-VQA features a highly scalable, human-in-the-loop annotation pipeline designed in two sequential stages.

### 🎬 Stage 1: Dense Sequential Captioning (`stage1_v2`)
This stage processes video chunks sequentially in chronological order. To maintain narrative consistency across chunks and video boundaries, it feeds previous caption summaries back to the LLM. It optimizes cost and context constraints using Gemini's **explicit context caching** to cache video inputs and system instructions, keeping only the sliding window text history uncached.

To run Stage 1 V2:
```powershell
python -m src.pipeline.stage1_v2 "<video_folder>" `
  --output "<narration_output_folder>" `
  --config "src\pipeline\conf\pipeline_v2.yaml" `
  -O stage1_model=gemini-3-flash-preview `
  -O stage1_fallback_model=gemini-3-flash-preview `
  --run-id "<run_id>"
```

#### Key Options:
*   `--output` or `-o`: Folder to save the generated caption narrations (default: saves alongside source videos).
*   `--model` or `-m`: Specify a custom Gemini model to use.
*   `--max-context` or `-c`: Set the maximum number of previous chunks in the sliding context window (default: `30`).
*   `--config`: Load the Hydra/OmegaConf pipeline config, for example `src\pipeline\conf\pipeline_v2.yaml`.
*   `--config-override` or `-O`: Repeatable Hydra-style override, for example `-O chunk_duration=60`.
*   `--run-id`: Optional stable identifier used in manifests and run-state logs.

---

### 📝 Stage 2: Question Generation & Verification (`stage2_loop_concurrent`)
This stage reads the narrations generated in Stage 1, creates a global **Super Ledger** of events, drafts challenging memory Q/A pairs, and submits them to an automated verifier loop. The verifier checks each pair for factual correctness, causality, and naturalness.

To run Stage 2 Loop Concurrent:
```powershell
python -m src.pipeline.stage2_loop_concurrent `
  "<narration_folder>" `
  "<video_folder>" `
  --output "<qa_output_folder>" `
  --config "src\pipeline\conf\pipeline_v2.yaml" `
  -O stage2_planner_model=gemini-3-flash-preview `
  -O stage2_retriever_model=gemini-3-flash-preview `
  -O stage2_verifier_model=gemini-3-flash-preview `
  -O stage2_enhancer_model=gemini-3-flash-preview `
  -O stage2_retriever_fallback_model=gemini-3-flash-preview `
  -O stage2_verifier_fallback_model=gemini-3-flash-preview `
  -O stage2_enhancer_fallback_model=gemini-3-flash-preview `
  --run-id "<run_id>"
```

#### Key Options:
*   `--output` or `-o`: Folder to save final Q/A pairs.
*   `--planner-model`: Custom Gemini model for question generation.
*   `--verifier-model`: Custom Gemini model for verification checks.
*   `--target` or `-t`: Target number of QA annotations.
*   `--qa-per-minute` or `-qpm`: Desired density of QA generation per minute of video.
*   `--global-qa-ratio` or `-g`: Proportion of global multi-evidence questions vs. localized ones (default: `0.5`).
*   `--generate-only`: Run the generator only, bypassing the automated verifier loop.
*   `--ledger-only` or `-l`: Compile the Super Ledger event database only.
*   `--max-loops`: Maximum loops of verification/re-generation to execute.
*   `--force` or `-f`: Force reprocessing, ignoring previous caches.
*   `--config`: Load the Hydra/OmegaConf pipeline config, for example `src\pipeline\conf\pipeline_v2.yaml`.
*   `--config-override` or `-O`: Repeatable Hydra-style override, for example `-O qa_batch_size=20`.
*   `--run-id`: Optional stable identifier used in manifests and run-state logs.

---

## 🎮 Starting the Annotation Review UI

Once the annotation pipeline generates Q/A pairs, you can inspect, verify, and refine them using our interactive review dashboard. 

The application utilizes a **Flask backend** and a **Svelte frontend**. Upon starting, the backend automatically detects Node.js and builds the Svelte app on the fly.

### Option A: Platform-Specific Startup Scripts (Recommended)

*   **Windows (PowerShell):**
    ```powershell
    .\start_server.ps1
    ```
*   **macOS / Linux (Bash):**
    ```bash
    chmod +x start_server.sh
    ./start_server.sh
    ```

These scripts automate virtual environment checks, load environment variables from `.env`, install missing Python packages, build/update Svelte assets, and start the local Flask server.

### Option B: Manual Startup
If you prefer running directly:
```bash
python app.py
```

### Accessing the Interface
Once the server starts up, open your web browser and navigate to:
*   💻 **Main UI:** `http://localhost:5000`
*   📖 **Interactive App & Docs:** `http://localhost:5000/app`

---

## 📄 Citation

If you use our dataset or code in your research, please cite our NeurIPS 2026 paper:

```bibtex
@inproceedings{supermemory_vqa2026,
  title={SuperMemory-VQA: An Egocentric Visual Question Answering Benchmark for Long-Horizon Memory},
  author={Anonymous Authors},
  booktitle={NeurIPS 2026 (Evaluations & Datasets Track)},
  year={2026},
  note={Under review}
}
```
