import { get } from 'svelte/store';
import { annotations, updateAnnotation, deleteAnnotation, setAnnotations } from '$lib/stores';
import { describe, beforeEach, test, expect } from 'vitest';
import type { Annotation } from '$lib/types';

describe('Store Reactivity', () => {
    beforeEach(() => {
        setAnnotations([]);
    });

    test('updateAnnotation creates a new array reference', () => {
        // Use a valid partial Annotation object, casting as any to bypass strict checks if needed for tests,
        // or better, use proper types. The store likely expects Annotation objects.
        // Let's create a minimal valid Annotation.
        const initial: Annotation[] = [{ question: 'test' }];
        setAnnotations(initial);

        const beforeUpdate = get(annotations);
        // updateAnnotation takes an index and a partial annotation (implied) or a full annotation?
        // Let's assume it replaces or merges. Based on previous code it seemed to merge or replace.
        // The previous code used { id: 1, text: 'test' } which implies the store might have been generic or changed.
        // Looking at types.ts, Annotation has 'question', 'answer' etc but no 'id' or 'text'.
        // I will use 'question' instead of 'text' to match the type.
        updateAnnotation(0, { question: 'updated' });
        const afterUpdate = get(annotations);

        expect(beforeUpdate).not.toBe(afterUpdate);
        expect(afterUpdate[0].question).toBe('updated');
    });

    test('deleteAnnotation creates a new array reference', () => {
        const initial: Annotation[] = [{ question: 'q1' }, { question: 'q2' }];
        setAnnotations(initial);

        const beforeDelete = get(annotations);
        deleteAnnotation(0);
        const afterDelete = get(annotations);

        expect(beforeDelete).not.toBe(afterDelete);
        expect(afterDelete.length).toBe(1);
    });
});
