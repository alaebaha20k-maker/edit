import React from 'react';
import {Composition} from 'remotion';
import {AlarTest} from './test';
export const Root:React.FC=()=> <Composition id="ALAR-Test" component={AlarTest} durationInFrames={180} fps={60} width={1080} height={1920}/>;
