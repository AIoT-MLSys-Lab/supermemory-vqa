<script lang="ts">
    import Button from "$lib/components/ui/button/Button.svelte";
    import { Chip, StatusBadge } from "./ui";

    interface Props {
        open: boolean;
        summaryData: Record<string, unknown>;
        onClose: () => void;
    }

    let { open, summaryData, onClose }: Props = $props();
</script>

{#if open && summaryData}
    <div
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        role="button"
        tabindex="0"
        onclick={onClose}
        onkeydown={(e) => {
            if (e.key === "Enter" || e.key === " ") onClose();
        }}
    >
        <div
            class="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden"
            role="dialog"
            aria-modal="true"
            tabindex="-1"
            onclick={(e) => e.stopPropagation()}
            onkeydown={(e) => e.stopPropagation()}
        >
            <div
                class="p-4 bg-card border-b border-border flex justify-between items-center"
            >
                <h2 class="text-xl font-bold text-foreground">
                    Annotation Summary
                </h2>
                <Button variant="ghost" onclick={onClose}>Close</Button>
            </div>
            <div class="p-6 overflow-y-auto max-h-[calc(90vh-80px)]">
                <!-- Summary Stats -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <div class="bg-primary/5 p-4 rounded-lg text-center">
                        <div class="text-3xl font-bold text-primary">
                            {summaryData.total_annotations || 0}
                        </div>
                        <div class="text-sm text-muted-foreground">
                            Total Annotations
                        </div>
                    </div>
                    <div class="bg-success/5 p-4 rounded-lg text-center">
                        <div class="text-3xl font-bold text-success">
                            {summaryData.reviewed_count || 0}
                        </div>
                        <div class="text-sm text-muted-foreground">
                            Reviewed
                        </div>
                    </div>
                    <div class="bg-warning/5 p-4 rounded-lg text-center">
                        <div class="text-3xl font-bold text-warning">
                            {summaryData.pending_count || 0}
                        </div>
                        <div class="text-sm text-muted-foreground">Pending</div>
                    </div>
                    <div class="bg-accent p-4 rounded-lg text-center">
                        <div class="text-3xl font-bold text-accent-foreground">
                            {(summaryData.annotation_files as Array<unknown>)
                                ?.length || 0}
                        </div>
                        <div class="text-sm text-muted-foreground">Files</div>
                    </div>
                </div>

                <!-- Skills Breakdown -->
                {#if summaryData.skills_breakdown && Object.keys(summaryData.skills_breakdown as Record<string, number>).length > 0}
                    <div class="mb-6">
                        <h3 class="font-semibold mb-2">Skills Breakdown</h3>
                        <div class="flex flex-wrap gap-2">
                            {#each Object.entries(summaryData.skills_breakdown as Record<string, number>) as [skill, count]}
                                <Chip
                                    value={skill}
                                    kind="skill"
                                    label="{skill}: {count}"
                                />
                            {/each}
                        </div>
                    </div>
                {/if}

                <!-- Annotation Files -->
                {#if summaryData.annotation_files}
                    <div class="mb-6">
                        <h3 class="font-semibold mb-2">Annotation Files</h3>
                        <div class="overflow-x-auto">
                            <table class="w-full border-collapse">
                                <thead>
                                    <tr class="bg-gray-100">
                                        <th class="border p-2 text-left"
                                            >File</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Count</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Reviewed</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Pending</th
                                        >
                                    </tr>
                                </thead>
                                <tbody>
                                    {#each summaryData.annotation_files as Array<{ filename: string; annotation_count: number; reviewed_count: number; pending_count: number }> as file}
                                        <tr class="hover:bg-gray-50">
                                            <td class="border p-2 text-sm"
                                                >{file.filename}</td
                                            >
                                            <td class="border p-2 text-center"
                                                >{file.annotation_count}</td
                                            >
                                            <td
                                                class="border p-2 text-center text-success"
                                                >{file.reviewed_count}</td
                                            >
                                            <td
                                                class="border p-2 text-center text-warning"
                                                >{file.pending_count}</td
                                            >
                                        </tr>
                                    {/each}
                                </tbody>
                            </table>
                        </div>
                    </div>
                {/if}

                <!-- Annotations Table -->
                {#if summaryData.annotations}
                    <div>
                        <h3 class="font-semibold mb-2">All Annotations</h3>
                        <div class="overflow-x-auto">
                            <table class="w-full border-collapse text-sm">
                                <thead>
                                    <tr class="bg-gray-100">
                                        <th class="border p-2 text-left"
                                            >File</th
                                        >
                                        <th class="border p-2 text-left"
                                            >Question</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Skill</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Status</th
                                        >
                                        <th class="border p-2 text-center"
                                            >Time</th
                                        >
                                    </tr>
                                </thead>
                                <tbody>
                                    {#each summaryData.annotations as Array<{ file: string; question: string; skill: string; review_status: string; time_span: { start?: string; end?: string } }> as ann}
                                        <tr class="hover:bg-gray-50">
                                            <td
                                                class="border p-2 truncate max-w-[150px]"
                                                title={ann.file}>{ann.file}</td
                                            >
                                            <td
                                                class="border p-2 truncate max-w-[200px]"
                                                title={ann.question}
                                                >{ann.question}</td
                                            >
                                            <td class="border p-2 text-center">
                                                <Chip
                                                    value={ann.skill}
                                                    kind="skill"
                                                />
                                            </td>
                                            <td class="border p-2 text-center">
                                                <StatusBadge
                                                    status={ann.review_status}
                                                />
                                            </td>
                                            <td class="border p-2 text-center"
                                                >{ann.time_span?.start ||
                                                    "-"}</td
                                            >
                                        </tr>
                                    {/each}
                                </tbody>
                            </table>
                        </div>
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}
