import React from "react";
import { Audio, Composition } from "remotion";
import { ReelComposition as AlexHormozi } from "../../templates/reels/alex-hormozi/ReelComposition";
import { ReelComposition as BrollCentric } from "../../templates/reels/b-roll-centric/ReelComposition";
import { ReelComposition as FacelessDocu } from "../../templates/reels/faceless-docu/ReelComposition";
import { ReelComposition as KineticBold } from "../../templates/reels/kinetic-bold/ReelComposition";
import { durationFromWords } from "./captioning/duration";

export type ReelWord = { word: string; start: number; end: number };
export type ReelScene = { id: string; assetUrl?: string; provider?: string };

export type ReelInputProps = {
  script: Array<{ id: string; voText: string }>;
  scenes: ReelScene[];
  audioSrc: string;
  words: ReelWord[];
  brandTokens: Record<string, string>;
  preset: string;
  presetTweaks: Record<string, unknown>;
  canvas: string;
  width: number;
  height: number;
};

const FPS = 30;
const FALLBACK_FRAMES = 900;

const VoiceoverTrack: React.FC<{ src: string }> = ({ src }) => (src ? <Audio src={src} /> : null);

const HormoziScene: React.FC<ReelInputProps> = (props) => {
  const tweak = props.presetTweaks.highlight;
  const highlight = typeof tweak === "string" ? tweak : "yellow";
  return (
    <>
      <AlexHormozi
        script={props.script}
        audioSrc={props.audioSrc}
        words={props.words}
        brandTokens={props.brandTokens}
        width={props.width}
        height={props.height}
        highlight={highlight}
      />
      <VoiceoverTrack src={props.audioSrc} />
    </>
  );
};

const BrollScene: React.FC<ReelInputProps> = (props) => {
  return (
    <>
      <BrollCentric
        script={props.script}
        audioSrc={props.audioSrc}
        words={props.words}
        brandTokens={props.brandTokens}
        width={props.width}
        height={props.height}
        scenes={props.scenes.map((scene) => ({ id: scene.id, assetUrl: scene.assetUrl }))}
      />
      <VoiceoverTrack src={props.audioSrc} />
    </>
  );
};

const DocuScene: React.FC<ReelInputProps> = (props) => {
  return (
    <>
      <FacelessDocu
        script={props.script}
        audioSrc={props.audioSrc}
        words={props.words}
        brandTokens={props.brandTokens}
        width={props.width}
        height={props.height}
        brollSrc={props.scenes[0]?.assetUrl}
      />
      <VoiceoverTrack src={props.audioSrc} />
    </>
  );
};

const KineticScene: React.FC<ReelInputProps> = (props) => {
  return (
    <>
      <KineticBold
        script={props.script}
        audioSrc={props.audioSrc}
        words={props.words}
        brandTokens={props.brandTokens}
      />
      <VoiceoverTrack src={props.audioSrc} />
    </>
  );
};

const baseDefaults: ReelInputProps = {
  script: [],
  scenes: [],
  audioSrc: "",
  words: [],
  brandTokens: {},
  preset: "",
  presetTweaks: {},
  canvas: "1080x1920",
  width: 1080,
  height: 1920,
};

const metadataFromProps = ({ props }: { props: ReelInputProps }) => ({
  durationInFrames: durationFromWords(props.words, FPS, FALLBACK_FRAMES),
  fps: FPS,
  width: props.width || 1080,
  height: props.height || 1920,
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="alex-hormozi"
        component={HormoziScene}
        durationInFrames={FALLBACK_FRAMES}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{ ...baseDefaults, preset: "alex-hormozi" }}
        calculateMetadata={metadataFromProps}
      />
      <Composition
        id="faceless-docu"
        component={DocuScene}
        durationInFrames={FALLBACK_FRAMES}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{ ...baseDefaults, preset: "faceless-docu" }}
        calculateMetadata={metadataFromProps}
      />
      <Composition
        id="b-roll-centric"
        component={BrollScene}
        durationInFrames={FALLBACK_FRAMES}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{ ...baseDefaults, preset: "b-roll-centric" }}
        calculateMetadata={metadataFromProps}
      />
      <Composition
        id="kinetic-bold"
        component={KineticScene}
        durationInFrames={FALLBACK_FRAMES}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{ ...baseDefaults, preset: "kinetic-bold" }}
        calculateMetadata={metadataFromProps}
      />
    </>
  );
};
