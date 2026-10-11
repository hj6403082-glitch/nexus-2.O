import { create } from 'zustand';
import { projectWorld, type ProjectWorld } from '@/knowledge/projectWorld';
import { useWorld, moduleWorld } from './world';
import { useNexus } from './nexus';
// Entering a project drops you into its own floating world. The environment
// settles on the Glass Observatory (the Projects world) so the island reads
// against a consistent room, and the derived grade/accent are cached here so
// the scene and the colour grade never recompute the hash per frame.
export type FocusedProject = { id: string; title: string; detail?: string };
type State = {
  focused: FocusedProject | null;
  world: ProjectWorld | null;
  enter: (project: FocusedProject) => void;
  exit: () => void;
};
export const useProject = create<State>((set, get) => ({
  focused: null, world: null,
  enter: project => {
    set({ focused: project, world: projectWorld(project) });
    // Hold the Observatory as the room and clear the panel so the island is
    // unobstructed. applyModule is skipped while focused (see Nexus), so the
    // world stays put until exit.
    useWorld.getState().set(moduleWorld.projects);
    useNexus.setState({ expanded: null });
    useNexus.getState().log(`${project.title.toUpperCase()} · entered world`);
  },
  exit: () => {
    if (!get().focused) return;
    set({ focused: null, world: null });
    // Return to whatever base world the user or weather had chosen.
    useWorld.getState().applyModule(null);
    useNexus.getState().log('Returned to orbit');
  },
}));
